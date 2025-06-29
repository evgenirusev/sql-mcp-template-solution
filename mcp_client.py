"""MCP client for database tool interactions."""

import json
from typing import Any, Optional
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

class MCPClient:
    """MCP Client following official documentation patterns."""
    
    def __init__(self):
        """Initialize the MCP client with proper resource management."""
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.available_tools = []
    
    async def connect_to_server(self, server_script_path: str = "sql_mcp_server.py"):
        """Connect to an MCP server and maintain persistent connection.
        
        Args:
            server_script_path: Path to the server script
        """
        server_params = StdioServerParameters(
            command="python",
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )

        await self.session.initialize()

        # Discover available tools dynamically
        response = await self.session.list_tools()
        self.available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]
        
        print(f"Connected to MCP server with tools: {[tool['name'] for tool in self.available_tools]}")
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool using the persistent session.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Tool execution result
            
        Raises:
            RuntimeError: If tool execution fails
            ValueError: If session is not initialized
        """
        if not self.session:
            raise ValueError("MCP session not initialized. Call connect_to_server() first.")
        
        try:
            raw_result = await self.session.call_tool(tool_name, arguments=arguments)
            
            # Log the raw MCP response for debugging
            print(f"  🔧 RAW MCP RESPONSE for {tool_name}:")
            print(f"     Type: {type(raw_result)}")
            print(f"     Dir: {[attr for attr in dir(raw_result) if not attr.startswith('_')]}")
            print(f"     Raw: {raw_result}")
            print()
            
        except Exception as e:
            raise RuntimeError(f"MCP tool '{tool_name}' execution failure: {e}")

        # Extract result from different MCP response formats
        result = getattr(raw_result, "result", getattr(raw_result, "data", raw_result))
        
        print(f"  📊 EXTRACTED RESULT for {tool_name}:")
        print(f"     Type: {type(result)}")
        print(f"     Content: {result}")
        print()

        # Handle direct dict/list results
        if isinstance(result, (list, dict)):
            print(f"  ✅ RETURNING DIRECT RESULT (list/dict)")
            return result

        # Handle content blocks (text responses)
        if hasattr(result, "content"):
            print(f"  📝 PROCESSING CONTENT BLOCKS (found {len(result.content)} blocks)")
            
            # Collect all parsed results from content blocks
            parsed_blocks = []
            raw_text_blocks = []
            
            for i, block in enumerate(result.content):
                if hasattr(block, "text"):
                    try:
                        parsed_json = json.loads(block.text)
                        parsed_blocks.append(parsed_json)
                        print(f"    Block {i+1}: Parsed JSON - {parsed_json}")
                    except json.JSONDecodeError:
                        raw_text_blocks.append(block.text)
                        print(f"    Block {i+1}: Raw text - {block.text}")
            
            # Return appropriate result based on what we found
            if parsed_blocks:
                if len(parsed_blocks) == 1:
                    print(f"  ✅ RETURNING SINGLE PARSED JSON: {parsed_blocks[0]}")
                    return parsed_blocks[0]
                else:
                    print(f"  ✅ RETURNING LIST OF PARSED JSON ({len(parsed_blocks)} items): {parsed_blocks}")
                    return parsed_blocks
            elif raw_text_blocks:
                if len(raw_text_blocks) == 1:
                    print(f"  ✅ RETURNING SINGLE RAW TEXT: {raw_text_blocks[0]}")
                    return raw_text_blocks[0]
                else:
                    print(f"  ✅ RETURNING LIST OF RAW TEXT ({len(raw_text_blocks)} items): {raw_text_blocks}")
                    return raw_text_blocks

        # Fallback for unexpected formats
        final_result = str(result)
        print(f"  ⚠️ FALLBACK TO STRING: {final_result}")
        return final_result
    
    def get_available_tools(self) -> list[dict]:
        """Get the list of available tools for OpenAI function calling.
        
        Returns:
            List of tool specifications in OpenAI format
        """
        return [{
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        } for tool in self.available_tools]
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        await self.exit_stack.aclose()

# Global MCP client instance
_mcp_client: Optional[MCPClient] = None

async def get_mcp_client() -> MCPClient:
    """Get or create the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
        await _mcp_client.connect_to_server()
    return _mcp_client

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Invoke any MCP tool with given arguments using persistent connection."""
    client = await get_mcp_client()
    return await client.call_tool(tool_name, arguments)

async def cleanup_mcp_client():
    """Clean up the global MCP client."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.cleanup()
        _mcp_client = None

def format_tool_result(func_name: str, result: Any) -> None:
    """Format and display tool execution results."""
    if func_name == "list_tables" and isinstance(result, list):
        # Log the raw result for debugging
        print(f"  🔍 RAW RESULT for {func_name}:")
        print(f"     Type: {type(result)}")
        print(f"     Length: {len(result)}")
        print(f"     Content: {result}")
        print()
        
        print(f"  → Found {len(result)} tables:")
        for table in result[:5]:  # Show first 5 tables
            print(f"    • {table.get('schema', 'dbo')}.{table.get('table', 'unknown')}")
        if len(result) > 5:
            print(f"    ... and {len(result) - 5} more tables")
    elif func_name == "describe_table" and isinstance(result, dict):
        table_name = result.get('table_name', 'unknown')
        columns = result.get('columns', [])
        print(f"  → Table '{table_name}' has {len(columns)} columns:")
        for col in columns[:3]:  # Show first 3 columns
            nullable = "NULL" if col.get('nullable') else "NOT NULL"
            print(f"    • {col.get('name')} ({col.get('type')}) {nullable}")
        if len(columns) > 3:
            print(f"    ... and {len(columns) - 3} more columns")
    elif func_name == "execute_sql" and isinstance(result, dict):
        if result.get("type") == "select":
            row_count = result.get('row_count', 0)
            print(f"  → Query returned {row_count} rows")
            if row_count > 0:
                rows = result.get('rows', [])
                if rows:
                    print(f"    Sample data: {list(rows[0].keys()) if rows else 'No columns'}")
                    # Show first row as example
                    if len(rows) > 0:
                        first_row = rows[0]
                        for k, v in list(first_row.items())[:3]:  # First 3 columns
                            print(f"      {k}: {v}")
        else:
            print(f"  → {result.get('message', 'Query executed')}")
            if 'rows_affected' in result:
                print(f"    Rows affected: {result['rows_affected']}")
    else:
        # Generic result logging for other cases
        print(f"  → Result: {str(result)[:100]}{'...' if len(str(result)) > 100 else ''}") 