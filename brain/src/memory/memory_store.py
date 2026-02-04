import lancedb
import time
from pathlib import Path
from .models import Memory, UserProfile

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data"

db = lancedb.connect(f"{DB_PATH}")

print(f"DB Connected at: {DB_PATH}")

class MemoryStore():
    def __init__(self):
       self.table = db.create_table("mashiro_memory", schema=Memory, exist_ok=True)

    def add_memory(self, text, user_id, user_name, role):
        # データの登録
        """
        memory_item = Memory(
            text=text,
            user_id=user_id,
            user_name=user_name,
            role=role,
            timestamp=time.time(),
            source="discord"
            )
        """

        # LanceDBに追加
        self.table.add([{
            "text": text,
            "user_id": user_id,
            "user_name": user_name,
            "role": role,
            "timestamp": time.time(),
            "source": "discord"
        }])

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

