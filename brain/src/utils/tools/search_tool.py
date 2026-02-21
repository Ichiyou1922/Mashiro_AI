from ddgs import DDGS
import json
from tavily import TavilyClient
import os
from dotenv import load_dotenv
load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

'''
def search_something(query: str) -> str:
    results = DDGS().text(
        query,
        region='jp-jp',
        safesearch='off',
        timelimit=None,
        page=3,
        max_results=3,
        backend="google",

        )
    title1 = results[0]["title"]
    body1 = results[0]["body"]
    title2 = results[1]["title"]
    body2 = results[1]["body"]
    title3 = results[2]["title"]
    body3 = results[2]["body"]
    result = (f"""
検索結果: {title1}
{body1}

検索結果: {title2}
{body2}

検索結果: {title3}
{body3}
""")
    return result
'''

def search_something(query: str) -> str:
    tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    response = tavily_client.search(
        query=f"{query}について日本語で詳細に要約し、回答してください。",
        search_depth="basic",
        include_answer=True,
        include_raw_content=False
    )
    if response["answer"]:
        return response["answer"]
    else:
        return "検索結果の取得に失敗しました。"
