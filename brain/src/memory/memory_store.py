import lancedb
import time
from pathlib import Path
from models import Memory

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
