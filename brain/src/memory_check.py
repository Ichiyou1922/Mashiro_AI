import lancedb
from pathlib import Path

# このファイルの親の親 (brain/) の data/ を参照
DB_PATH = Path(__file__).resolve().parent.parent / "data"
db = lancedb.connect(str(DB_PATH))
table = db.open_table('mashiro_memory')
df = table.to_pandas()

# 最新5件（見やすく整形）
recent = df.sort_values('timestamp', ascending=False).head(5)
print("=== 最新の記憶 ===")
for _, row in recent.iterrows():
    print(f"[{row['user_name']}] {row['text'][:80]}...")
    print()

# 全件数
print(f"総記憶数: {len(df)}")