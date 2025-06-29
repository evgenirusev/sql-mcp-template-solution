"""SQL AI Agent Console - Main chat interface for database queries."""

import asyncio
import json
import openai
from config import API_KEY, SYSTEM_PROMPT, OPENAI_MODEL, MAX_CONVERSATION_HISTORY
from mcp_client import get_mcp_client, call_mcp_tool, format_tool_result, cleanup_mcp_client

# Main chat loop

async def chat_loop() -> None:
    openai_client = openai.OpenAI(api_key=API_KEY)
    
    # Initialize MCP client and get available tools
    mcp_client = await get_mcp_client()
    functions_spec = mcp_client.get_available_tools()
    
    conversation: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    print("💬 SQL Assistant Ready! Ask me anything about the database (Ctrl-C to quit)\n")

    while True:
        user_input = input("User > ")
        if not user_input.strip():
            continue
        
        conversation.append({"role": "user", "content": user_input})

        while True:  # loop until we have a final assistant message
            # Trim conversation history if too long
            if len(conversation) > MAX_CONVERSATION_HISTORY:
                conversation = [conversation[0]] + conversation[-(MAX_CONVERSATION_HISTORY-1):]
            
            # Ask the model – function-calling aware request
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=conversation,
                tools=functions_spec,
            )

            msg_obj = response.choices[0].message  # ChatCompletionMessage

            # Handle multiple tool calls in one response
            if msg_obj.tool_calls:
                tool_results = []
                
                for tool_call in msg_obj.tool_calls:
                    func_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    print(f"▪ Executing {func_name}({arguments})")
                    
                    try:
                        result = await call_mcp_tool(func_name, arguments)
                        format_tool_result(func_name, result)

                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps(result)
                        })
                    except Exception as e:
                        print(f"  ❌ Error: {e}")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps({"error": str(e)})
                        })

                # Add assistant message with tool calls
                conversation.append(msg_obj.model_dump(exclude_none=True))
                # Add all tool results
                conversation.extend(tool_results)
                continue  # ask model to produce a final answer

            # Final response
            conversation.append({"role": "assistant", "content": msg_obj.content})
            print(f"Assistant > {msg_obj.content}\n")
            break


if __name__ == "__main__":
    try:
        asyncio.run(chat_loop())
    except (KeyboardInterrupt, EOFError):
        print("\nBye!")
    finally:
        # Clean up MCP client resources
        try:
            asyncio.run(cleanup_mcp_client())
        except:
            pass  # Ignore cleanup errors during shutdown 