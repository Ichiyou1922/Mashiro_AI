import sys
import os
from dotenv import load_dotenv
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from groq import Groq


load_dotenv()

GROQ_KEY = os.getenv("GROQ_API")
groq_client = Groq(
    api_key=os.environ.get("GROQ_API_KEY", f"{GROQ_KEY}")
    )
groq_model = "meta-llama/llama-4-scout-17b-16e-instruct"

def analyze_image(url: str) -> str:
    message = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "この画像を日本語で説明してください。特徴的な部分があれば強調してください。"},
                {"type": "image_url", "image_url": {"url": url}}
            ]
        }
    ]

    response = groq_client.chat.completions.create(
        model=groq_model,
        messages=message
    )

    answer_text: str = response.choices[0].message.content or ""
    if answer_text:
        return answer_text
    else:
        return_text = "画像情報の取得に失敗しました。"
        return return_text

