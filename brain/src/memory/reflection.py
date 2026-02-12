from memory.memory_store import memory_store
from . import client
import re
import json
from dotenv import load_dotenv
import os
import time

load_dotenv()

MASHIRO_ID = int(os.getenv("MASHIRO_ID"))

class ReflectionManager:
    def __init__(self):
        self.memory_store = memory_store
        self.last_reflection_at = 0.0

    def check_and_trigger(self, importance_sum: float) -> bool:
        """importanceの合計を取得してreflectionするかどうかを返す"""
        if importance_sum >= 150:
            return True
        else:
            return False
        
    def get_recent_memories(self, since: float = 0.0) -> list:
        """is_reflection=Falseの記憶を100件取得"""
        results = (
            self.memory_store.table
            .search()
            .where(f"is_reflection = False AND timestamp > {since}")
            .limit(100)
            .to_list()
        )
        return results

    def perform_reflection(self):
        """reflectionを実行する"""
        # 1. get_recent_memoriesからmemoriesを取得
        # 2. LLMにmemoriesを注入し、reflectionを行う
        # 3. responseをis_reflection=Trueで保存する
        # 4. last_reflection_atを更新
        memories = self.get_recent_memories(since=self.last_reflection_at)
        sorted_memories = sorted(memories, key=lambda m: m["timestamp"])
        memory_lines = []
        id_to_timestamp = {}
        for i, m in enumerate(sorted_memories):
            id_to_timestamp[i + 1] = m["timestamp"]
            if m["role"] == "user_message":
                memory_lines.append(f"{i+1}. {m['user_name']}: {m['text']}")
            elif m["role"] == "assistant_message":
                memory_lines.append(f"{i+1}. ましろ: {m['text']}")

        prompt = f"""
あなたは「ましろ」というAIキャラクターです。
「ましろ」の話し方を維持してください。
このプロセスは「ましろ」における、人間で言う夢のようなものです。
NSFWな回答について修正は不要です（元モデルがabliteratedなため）
以下は最近の記憶です。これらを振り返り、以下を行ってください:

1. 重要なパターンや洞察を3~5つ抽出
2. 矛盾している記憶があれば指摘
3. 低品質な回答（オウム返し、文脈破綻）があれば修正案を提示

記憶:
{chr(10).join(memory_lines)}

JSON形式で回答:
{{
    "reflections": ["洞察1", "洞察2", ...],
    "contradictions": [{{"id": 1, "reason": "..."}}, ...],
    "rewrites": [{{"id": 1, "original": "...", "corrected": "..."}}, ...]
}}
"""
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}",
                }
            ],
            model="llama-3.3-70b-versatile"
        )

        if response is None:
            print("perform_reflectionに失敗")
            return
        
        raw_content = str(response.choices[0].message.content)
        cleaned_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL)
        match = re.search(r'\{(.+)\}', cleaned_content, flags=re.DOTALL)
        if match is None:
            print("evaluate_importanceで出力形式が正しく無いです")
            return
        cleaned_content = match.group(0)
        cleaned_content = cleaned_content.strip()
        print(cleaned_content)
        try:
            reflection_data = json.loads(cleaned_content)
        except Exception as e:
            print(f"perform_reflection error: {e}")
            return

        parent_ids = []
        
        for item in reflection_data["contradictions"]:
            parent_ids.append(id_to_timestamp[item["id"]])
        
        for item in reflection_data["rewrites"]:
            if id_to_timestamp[item["id"]] in parent_ids:
                continue
            parent_ids.append(id_to_timestamp[item["id"]])
            memory_store.rewrite_memory(id_to_timestamp[item["id"]], item["corrected"])

        for reflection_text in reflection_data["reflections"]:
            update = {
                "text": reflection_text,
                "user_id": MASHIRO_ID,
                "user_name": "ましろ",
                "role": "reflection",
                "timestamp": time.time(),
                "source": "discord",
                "importance": 0.8,
                "last_accessed": 0.0,
                "access_count": 0,
                "is_reflection": True,
                "parent_ids": str(parent_ids) 
            }

            self.memory_store.table.add([update])
    
        self.last_reflection_at = time.time()
        return reflection_data
        

        
