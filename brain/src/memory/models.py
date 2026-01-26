import lancedb
from lancedb.pydantic import LanceModel, Vector
from lancedb.embeddings import get_registry
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data"

model = get_registry().get("sentence-transformers").create(name="intfloat/multilingual-e5-large")

class Memory(LanceModel):
    # ベクトルデータ（検索用）
    vector: Vector(model.ndims()) = model.VectorField()

    # 会話の中身（LLMが読む）
    text: str = model.SourceField()

    # MetaData
    user_id: int # discord user ID
    user_name: str
    role: str
    timestamp: float

    # extention
    # emotion: str = "neutral"
    source: str = "discord"

    