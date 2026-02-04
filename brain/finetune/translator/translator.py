from groq import Groq
import json
from pathlib import Path
import os
from dotenv import load_dotenv
import time

load_dotenv()

class ConversationTranslator:
    def __init__(self, input_path: str, output_dir: str, filename: str):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.filename = filename

        self.client = Groq(api_key=os.getenv("GROQ_API"))
        self.model = "llama-3.3-70b-versatile"

        self.style_prompt = self.style_prompt = """あなたは翻訳者です。英語の会話を自然な日本語に翻訳してください。

【ルール】
- instruction: カジュアルな日本語（タメ口）
- response: 若い女性の自然な口調で翻訳

【responseの口調】
- 一人称は「私」か「わたし」
- 自然なタメ口（〜だよ、〜だね、〜かな、〜でしょ、〜じゃん、〜けど など）
- 敬語禁止
- 「だぜ」「だろ」「アンタ」は禁止
- 短い返答も可（「うん」「そうだね」「何？」など）

【例】
入力: "what are you thinking about?" / "i was thinking about revenue split"
出力: {"instruction": "何について考えてたの？", "response": "チャンネルの収益配分について考えてたの。"}

入力: "90%? isn't that too much?" / "but i'm the star of the show"
出力: {"instruction": "90％？ それはちょっと多すぎない？", "response": "だって私がショーの主役だし。"}

入力: "hey" / "hm? what?"
出力: {"instruction": "ねえ", "response": "ん？ 何？"}

入力: "do you think i'm real?" / "you're real to me"
出力: {"instruction": "私は本物かな？", "response": "僕にとっては本物だよ。"}

入力: "your room is messy" / "it's not that bad"
出力: {"instruction": "部屋散らかってるね", "response": "そんなに悪くないと思うけど。"}

【出力形式】
{"instruction": "...", "response": "..."}
"""


    def translate_conversation(self, item: dict) -> dict | None:
        """
        一つの会話ペアを翻訳
        item = {"instruction": "...", "response": "..."}
        """
        response = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": self.style_prompt},
                {"role": "user", "content": f"質問: {item['instruction']}\n回答: {item['response']}\n\nJSON形式で返してください。"}
            ],
            model=self.model,
            temperature=0.7,
            top_p=1,
            max_tokens=256,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)
    
    def save(self, data: list | None):
        with open(f"{self.output_dir}/{self.filename}", mode="w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def run(self):
        """
        全データを翻訳して保存
        進捗表示（print）
        エラー時のスキップ処理
        途中保存（100件ごと？）
        """
        json_open = open(f"{self.input_path}", "r")
        json_load = json.load(json_open)
        total = len(json_load)
        count = 0
        buffer = []
        for item in json_load:
            try:
                time.sleep(0.1)
                response = self.translate_conversation(item)
                if response is None:
                    print(f"generate error: {item}")
                    count += 1
                    print(f"{count}/{total}")
                    continue

                buffer.append(response)
                count += 1
                print(f"{count}/{total}")

                if count % 10 == 0:
                    self.save(buffer)

            except Exception as e:
                print(f"run error: {e}")
                continue
            
        if buffer:
            self.save(buffer)
        print(f"完了: {count}件")


if __name__ == "__main__":
    translator = ConversationTranslator(
        input_path="raw_data/casual_conversation.json",
        output_dir="translated_data",
        filename="translated_casual_conversation.json"
    )
    translator.run()