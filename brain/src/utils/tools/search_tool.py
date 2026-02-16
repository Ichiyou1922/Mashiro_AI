from ddgs import DDGS
import json

def search_something(query: str) -> str:
    results = DDGS().text(
        query,
        region='jp-jp',
        safesearch='off',
        timelimit=None,
        page=1,
        max_results=1,
        backend="auto"
        )
    title = results[0]["title"]
    body = results[0]["body"]
    result = (f"""
検索結果: {title}
{body}
""")
    return result
