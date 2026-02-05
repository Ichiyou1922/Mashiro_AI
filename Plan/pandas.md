# Pandas 基礎知識

LanceDBなどのデータベースから取得したデータを操作する際によく使うpandasの基本操作をまとめる。

## DataFrameとは

pandasの基本データ構造。表形式のデータを扱う。

```python
import pandas as pd

# 例: LanceDBからDataFrameを取得
df = table.to_pandas()

# 中身のイメージ
#    user_id  display_name  timestamp
# 0    123    "太郎"         1706123456
# 1    456    "花子"         1706123789
# 2    123    "太郎"         1706124000
```

## よく使う操作

### フィルタリング（条件で行を抽出）

```python
# user_id が 123 の行だけ取得
filtered = df[df["user_id"] == 123]

# 複数条件（AND）
filtered = df[(df["user_id"] == 123) & (df["role"] == "user")]

# 複数条件（OR）
filtered = df[(df["user_id"] == 123) | (df["user_id"] == 456)]
```

### ソート（並び替え）

```python
# timestamp で昇順ソート（古い順）
sorted_df = df.sort_values("timestamp", ascending=True)

# timestamp で降順ソート（新しい順）
sorted_df = df.sort_values("timestamp", ascending=False)

# 複数カラムでソート
sorted_df = df.sort_values(["user_id", "timestamp"], ascending=[True, False])
```

### 先頭/末尾を取得

```python
# 先頭5行を取得
top5 = df.head(5)

# 末尾5行を取得
bottom5 = df.tail(5)

# 先頭10行（デフォルト）
top10 = df.head()
```

### 空かどうかチェック

```python
if df.empty:
    print("データがありません")
else:
    print(f"{len(df)}件のデータがあります")
```

### 特定の値を取得

```python
# iloc: インデックス番号で取得（0始まり）
first_row = df.iloc[0]           # 最初の行（Series）
first_name = df["display_name"].iloc[0]  # 最初の行のdisplay_name

# loc: ラベルで取得（あまり使わない）
# df.loc[0, "display_name"]
```

### 辞書/リストに変換

```python
# 辞書のリストに変換（各行が辞書になる）
records = df.to_dict("records")
# [{"user_id": 123, "display_name": "太郎", ...}, {...}]

# 通常の辞書に変換（カラムがキー）
dict_data = df.to_dict()
# {"user_id": {0: 123, 1: 456}, "display_name": {0: "太郎", 1: "花子"}}
```

## 実践例（memory_store.py で使用）

### get_recent: 最近の会話を取得

```python
def get_recent(self, user_id: int, limit: int = 10) -> list:
    # 1. テーブル全体をDataFrameとして取得
    df = self.table.to_pandas()

    # 2. user_id でフィルタ
    filtered = df[df["user_id"] == user_id]

    # 3. timestamp で降順ソート（新しい順）
    sorted_df = filtered.sort_values("timestamp", ascending=False)

    # 4. 先頭 limit 件を取得
    top_n = sorted_df.head(limit)

    # 5. 辞書のリストに変換して返す
    return top_n.to_dict("records")
```

### get_name: ユーザー名を取得

```python
def get_name(self, user_id: int) -> str | None:
    # 1. テーブル全体をDataFrameとして取得
    df = self.table.to_pandas()

    # 2. user_id でフィルタ
    filtered = df[df["user_id"] == user_id]

    # 3. 空チェック（該当ユーザーがいない場合）
    if filtered.empty:
        return None

    # 4. 最初の行の display_name を返す
    return filtered["display_name"].iloc[0]
```

## 注意点

### iloc vs 直接アクセス

```python
# NG: フィルタ後のDataFrameに直接 [0] でアクセスするとエラーになることがある
# filtered[0]  # KeyError の可能性

# OK: iloc を使う
filtered.iloc[0]

# OK: カラム指定してから iloc
filtered["display_name"].iloc[0]
```

### empty チェックは必須

```python
# NG: 空のDataFrameで iloc[0] するとエラー
filtered = df[df["user_id"] == 999]  # 該当なし
name = filtered["display_name"].iloc[0]  # IndexError!

# OK: 先に empty チェック
if filtered.empty:
    return None
return filtered["display_name"].iloc[0]
```

### メモリに注意

```python
# to_pandas() はテーブル全体をメモリに読み込む
# 大量データの場合はLanceDBのwhere/limitを先に使う

# 小規模データなら問題なし
df = self.table.to_pandas()

# 大規模データの場合は事前にフィルタ
# （ただしUserProfileは少量なので問題なし）
```
