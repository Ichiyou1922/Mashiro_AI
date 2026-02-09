import lancedb
from lancedb.pydantic import LanceModel, Vector
from lancedb.embeddings import get_registry
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data"

model = get_registry().get("sentence-transformers").create(name="BAAI/bge-m3")

class Memory(LanceModel):
    # ベクトルデータ（検索用）
    vector: Vector(model.ndims()) = model.VectorField()

    # 会話の中身（LLMが読む）
    text: str = model.SourceField()

    # MetaData
    user_id: int # discord user ID
    user_name: str
    role: str # "user_message" | "assistant_message" | "reflection" | "self_talk" | "observation" | "plan"
    timestamp: float

    # extension
    # emotion: str = "neutral"
    source: str = "discord"

    # memory stream
    importance: float = 0.0 # 0.0 = 未評価, 1-10を正規化
    last_accessed: float = 0.0 # 最終参照時刻
    access_count: int = 0
    is_reflection: bool = False
    parent_ids: str = "" # 統合元の記憶ID

class UserProfile(LanceModel):
    user_id: int
    display_name: str
    updated_at: float
    