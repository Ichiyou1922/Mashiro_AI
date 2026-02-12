import re

# text = "<function=time_tool>{{}}</function>"

def parse_tool(text: str) -> dict | str | None:
    match = re.search(r'<function=(.+?)>{(.*)}</function>', text)
    tools = [
        "time_tool",
        "date_tool"
    ]

    if match:
        tool = match.group(1)
        param = match.group(2)
        if tool in tools:
            print("===function calling!===")
            print(f"function calling: {tool}")
            print(f"param: {param}")
            return {"tool_name": tool, "param": f"{{{param}}}"}
        else:
            print("function is not found")
            return None
    else:
        return text

# parse_tool(text)