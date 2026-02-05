# memory_check.py を参考に
import lancedb
from pathlib import Path

DB_PATH = Path("brain/data")
db = lancedb.connect(str(DB_PATH))
table = db.open_table('mashiro_memory')
df = table.to_pandas()

# 「キュゥーッ」を含むレコードを検索
kyuu_records = df[df['text'].str.contains('キュゥーッ', na=False)]
print(f"「キュゥーッ」を含む記憶数: {len(kyuu_records)}")
print(f"全記憶数: {len(df)}")
print(f"割合: {len(kyuu_records)/len(df)*100:.1f}%")
