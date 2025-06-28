"""MCP client for database tool interactions."""

import json
from typing import Any
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Invoke any MCP tool with given arguments."""
    params = StdioServerParameters(command="python", args=["sql_mcp_server.py"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                raw = await session.call_tool(tool_name, arguments=arguments)
            except Exception as e:
                raise RuntimeError(f"MCP tool '{tool_name}' execution failure: {e}")

            # Extract result from different MCP response formats
            result = getattr(raw, "result", getattr(raw, "data", raw))

            # Handle direct dict/list results
            if isinstance(result, (list, dict)):
                return result

            # Handle content blocks (text responses)
            if hasattr(result, "content"):
                for block in result.content:
                    if hasattr(block, "text"):
                        try:
                            return json.loads(block.text)
                        except json.JSONDecodeError:
                            return block.text

            # Fallback for unexpected formats
            return str(result)

def format_tool_result(func_name: str, result: Any) -> None:
    """Format and display tool execution results."""
    if func_name == "list_tables" and isinstance(result, list):
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