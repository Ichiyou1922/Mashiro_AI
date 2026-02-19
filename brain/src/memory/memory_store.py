import lancedb
import time
from pathlib import Path
from .models import Memory, UserProfile
from . import client
import json
import re
from collections import deque


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data"

db = lancedb.connect(f"{DB_PATH}")

print(f"DB Connected at: {DB_PATH}")

class MemoryStore():
    def __init__(self):
       self.table = db.create_table("mashiro_memory", schema=Memory, exist_ok=True)
       self.short_term = deque(maxlen=16)

    def add_memory(self, text, user_id, user_name, role):
        current_time = time.time()
        # LanceDBに追加
        self.table.add([{
            "text": text,
            "user_id": user_id,
            "user_name": user_name,
            "role": role,
            "timestamp": current_time,
            "source": "discord",
            "importance": 0.0,
            "last_accessed": time.time(),
            "access_count": 0,
            "is_reflection": False,
            "parent_ids": ""

        }])

        self.short_term.append({
            "text": text,
            "role": role,
            "user_name": user_name,
            "timestamp": current_time
        })
        return current_time

    def search_memory(self, query: str, limit: int = 5):
        """
        queryに関連する記憶をベクトル検索で取得
        - user_idを指定すると、そのユーザーの記憶のみ検索
        - LanceDBの .search(query).limit(limit) を使う
        - textフィールドのみを返す（ベクトルデータを除外）
        """
        search_query = f"query: {query}"
        return self.table.search(search_query).limit(limit).to_list()

    def get_recent(self, user_id: int, limit: int = 10) -> list:
        """
        指定ユーザーの最近の会話を時系列で取得
        - .to_pandas()かSQL的クエリ
        - timestampで降順ソート
        """
        dataset = self.table.to_lance()
        results = (
            dataset
            .to_table(filter=f"user_id = {int(user_id)}")
            .to_pandas()
            .sort_values("timestamp", ascending=False)
            .head(limit)
            .to_dict("records")
        )
        return results

    def get_reflection(self, limit=3):
        results = (
            self.table
            .search()
            .where("is_reflection = True")
            .to_list()  # limitなし
        )
        sorted_results = sorted(results, key=lambda x: x["timestamp"], reverse=True)
        return sorted_results[:limit]


        
    
    def get_short_term(self) -> list:
        return list(self.short_term)
    
    def search_with_score(self, query: str, limit: int = 4) -> list | None:
        """recency * importance * relevanceでスコアリング検索"""
        current_time = time.time()
        short_terms = self.get_short_term()
        remove_timestamps = {item["timestamp"] for item in short_terms}
        # relevance 重視で候補を取得
        candidates = self.table.search(query).limit(limit * 3).to_list()
        candidates = [c for c in candidates if c["timestamp"] not in remove_timestamps]

        before_sort = []

        # 各候補のスコア計算
        for memory in candidates:
            recency = 0.995 ** ((current_time - memory["last_accessed"]) / 1200.0) # 20分を目安に計算
            importance = memory["importance"] # 正規化済み
            relevance = 1.0 - memory["_distance"]

            score = recency + importance + relevance
            before_sort.append([memory, score])

        sorted_list = sorted(before_sort, key=lambda x: x[1], reverse=True)
        reflection_list = [rl for rl in sorted_list if rl[0]["is_reflection"] == True]
        memory_list = [ml for ml in sorted_list if ml[0]["is_reflection"] == False]

        result_list = reflection_list[:1] + memory_list

        if result_list is None:
            return None
        
        return [row[0] for row in result_list][:limit]

    def update_importance(self, timestamps: list, scores: list):
        """バッチでimportance更新"""
        for i in range(len(timestamps)):
            results = (
                self.table
                .search()
                .where(f"timestamp = {timestamps[i]}")
                .limit(1)
                .to_list()
            )

            if not results:
                continue

            memory = results[0]

            updates = {
                "text": memory["text"],
                "user_id": memory["user_id"],
                "user_name": memory["user_name"],
                "role": memory["role"],
                "timestamp": memory["timestamp"],
                "source": "discord",
                "importance": scores[i] / 10.0,
                "last_accessed": memory["last_accessed"],
                "access_count": memory["access_count"],
                "is_reflection": memory["is_reflection"],
                "parent_ids": memory["parent_ids"]
            }

            (
                self.table.merge_insert("timestamp")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute([updates])
            )

    def get_pending_evaluation(self, limit: int = 50) -> list:
        """importance未評価の記憶を取得"""
        result = (
            self.table
            .search()
            .where(f"importance = 0.0")
            .limit(limit)
            .to_list()
        )
        return result
    
    def evaluate_importance(self):
        """impotance未評価の記憶を評価する"""
        pending = self.get_pending_evaluation(limit=50)
        if not pending:
            return
        
        # プロンプト構築(id -> timestampのマッピングを保持)
        id_to_timestamp = {}
        memory_lines = []
        for i, memory in enumerate(pending):
            id_to_timestamp[i + 1] = memory["timestamp"]
            memory_lines.append(f'{i + 1}. "{memory["text"]}"')

        prompt = f"""
以下の会話記録それぞれについて、1~10の重要度スコアをつけてください。
重要度の基準:
- 1-3: 日常的な挨拶、雑談
- 4-6: 一般的な情報交換、質問と回答
- 7-9: 個人的な情報、感情表現、重要な出来事
- 10: 人生の転機、深い信頼関係に関わる発言

{chr(10).join(memory_lines)}

JSON形式で回答: [{{"id": 1, "score": 5}}, ...]
"""
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}",
                }
            ],
            model="qwen/qwen3-32b"
        )

        if response is None:
            print("evaluate_importanceに失敗")
            return

        raw_content = str(response.choices[0].message.content)
        cleaned_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL)
        match = re.search(r'\[(.+)\]', cleaned_content, flags=re.DOTALL)
        if match is None:
            print("evaluate_importanceで出力形式が正しく無いです")
            return
        cleaned_content = match.group(0)
        cleaned_content = cleaned_content.strip()
        try:
            scores_data = json.loads(cleaned_content)
        except Exception as e:
            print(f"evaluate_importance error: {e}")
            print(json.loads(cleaned_content))
            return

        timestamps = []
        scores = []
        for item in scores_data:
            timestamps.append(id_to_timestamp[item["id"]])
            scores.append(item["score"])
        
        self.update_importance(timestamps, scores)
        print("importance評価が完了しました")

    def adjust_importance(self, timestamp: float, delta: float):
        """importanceを増減する(-1.0~1.0の範囲で)"""
        results = (
            self.table
            .search()
            .where(f"timestamp = {timestamp}")
            .limit(1)
            .to_list()
        )
        
        if not results:
            print("記憶が見つかりませんでした(adjust_importance)")
            return
        
        memory = results[0]
        current_importance = memory["importance"]
        result_importance = current_importance + delta
        result_importance = max(0.0, min(1.0, result_importance))

        updates = {
            "text": memory["text"],
            "user_id": memory["user_id"],
            "user_name": memory["user_name"],
            "role": memory["role"],
            "timestamp": memory["timestamp"],
            "source": "discord",
            "importance": result_importance,
            "last_accessed": memory["last_accessed"],
            "access_count": memory["access_count"],
            "is_reflection": memory["is_reflection"],
            "parent_ids": memory["parent_ids"]
        }

        (
            self.table.merge_insert("timestamp")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute([updates])
        )

    def rewrite_memory(self, timestamp: str, new_text: str):
        """汚染された記憶を書き換え"""
        results = (
            self.table
            .search()
            .where(f"timestamp = {timestamp}")
            .limit(1)
            .to_list()
        )
        if not results:
            print("記憶が見つかりませんでした(rewrite_memory)")
            return None

        memory = results[0]

        updates = {
                "text": new_text,
                "user_id": memory["user_id"],
                "user_name": memory["user_name"],
                "role": memory["role"],
                "timestamp": memory["timestamp"],
                "source": "discord",
                "importance": memory["importance"],
                "last_accessed": memory["last_accessed"],
                "access_count": memory["access_count"],
                "is_reflection": memory["is_reflection"],
                "parent_ids": memory["parent_ids"]
            }
        
        (
            self.table.merge_insert("timestamp")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute([updates])
        )

    def mark_accessed(self, timestamps: list):
        """last_accessedとaccess_countを更新"""
        current_time = time.time()

        for ts in timestamps:
            results = (
                self.table
                .search()
                .where(f"timestamp = {ts}")
                .limit(1)
                .to_list()
            )

            if not results:
                continue

            memory = results[0]

            updates = {
                "text": memory["text"],
                "user_id": memory["user_id"],
                "user_name": memory["user_name"],
                "role": memory["role"],
                "timestamp": ts,
                "source": "discord",
                "importance": memory["importance"],
                "last_accessed": current_time,
                "access_count": memory["access_count"] + 1,
                "is_reflection": memory["is_reflection"],
                "parent_ids": memory["parent_ids"]
            }

            (
                self.table.merge_insert("timestamp")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute([updates])
            )
    
    def get_importance_sum(self, since = 0.0) -> float:
        importance_sum = 0.0

        results = (
            self.table
            .search()
            .where(f"is_reflection = False AND timestamp > {since}")
            .to_list()
        )

        for result in results:
            importance = result["importance"]
            importance_sum += importance

        return importance_sum
        
    
class UserProfileStore:
    def __init__(self):
        # schema=UserProfileで作成
        self.table = db.create_table("user_profiles", schema=UserProfile, exist_ok=True)

    def set_name(self, user_id: int, display_name: str):
        """
        名前を登録・更新
        - 既存ユーザーがいれば更新、いなければ追加
        - LanceDBのupseartを使う
        """
        new_users = {"user_id": user_id, "display_name": display_name, "updated_at": time.time()}

        (
            self.table.merge_insert("user_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute([new_users])
        )

    def get_name(self, user_id: int) -> str:
        """
        user_idから名前を取得
        - user_idと紐付いた名前を1件取得 -> 登録されていないならそれを伝える文を
        """
        results = (
            self.table
            .search()
            .where(f"user_id = {int(user_id)}")
            .limit(1)
            .to_list()
        )
        if not results:
            return "ましろが名前を知らない人です"
        return results[0]["display_name"]

memory_store = MemoryStore()