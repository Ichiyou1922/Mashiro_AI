import re

# text = "<tool>time_tool</tool>"

def parse_tool(text: str) -> str | None:
    match = re.search(r'<tool>(.+?)</tool>', text)
    tools = [
        "time_tool",
        "date_tool"
    ]

    if match:
        tool = match.group(1)
        if tool in tools:
            print(f"function calling: {tool}")
            return tool
        else:
            print("function is not found")
            return None
    else:
        return text

# parse_tool(text)