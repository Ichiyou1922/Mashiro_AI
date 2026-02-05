# Jupyter Notebook (.ipynb) の思考法

## 通常のPythonとの根本的な違い

### パラダイムの比較

| 観点 | 通常のPython (.py) | Jupyter Notebook (.ipynb) |
|------|-------------------|---------------------------|
| **実行モデル** | トップダウン、一括実行 | セル単位、対話的 |
| **状態管理** | 毎回リセット | カーネル内で状態保持 |
| **設計思想** | 完成品として動く | 実験・探索の過程を記録 |
| **再現性** | 高い（同じ結果） | 低い（実行順序依存） |
| **用途** | プロダクション、ライブラリ | 研究、プロトタイプ、学習 |

---

## .py の思考法：「設計図を書く」

```python
# main.py - 完成品として設計

class DataProcessor:
    def __init__(self, config):
        self.config = config

    def load(self, path):
        ...

    def process(self):
        ...

    def save(self, path):
        ...

def main():
    processor = DataProcessor(config)
    processor.load("data.json")
    processor.process()
    processor.save("output.json")

if __name__ == "__main__":
    main()
```

**特徴**:
- 全体の構造を先に考える
- クラス、関数で抽象化
- エラーハンドリングを組み込む
- 他の人が使うことを想定
- テストを書ける形

---

## .ipynb の思考法：「実験ノートを書く」

### セル1: 環境構築
```python
# 最初に必ず環境を整える
!pip install transformers
import torch
print(f"GPU: {torch.cuda.is_available()}")
```

### セル2: データ確認
```python
# データを「見る」ことが目的
import json
with open("data.json") as f:
    data = json.load(f)

print(f"データ数: {len(data)}")
print(f"サンプル: {data[0]}")
```

### セル3: 実験
```python
# 仮説を検証する
# このセルは何度も書き換える
result = some_experiment(data)
result  # 最後の行は自動で表示される
```

### セル4: 可視化
```python
# 結果を「見える化」する
import matplotlib.pyplot as plt
plt.plot(result)
plt.show()
```

---

## 重要な概念：カーネルの状態

```
┌─────────────────────────────────────┐
│         Jupyter Kernel              │
│                                     │
│  変数: data, model, result, ...     │
│  インポート: torch, numpy, ...       │
│  状態: GPU使用中、ファイルオープン    │
│                                     │
│  ← セルを実行するたびに蓄積          │
└─────────────────────────────────────┘
```

**注意点**:
- セルの「見た目の順番」と「実行した順番」は違うかもしれない
- 変数を上書きしても、以前の値を参照しているセルがある
- `Kernel > Restart` で状態をリセット

---

## ipynbでの設計パターン

### パターン1: 段階的詳細化

```
セル1: 全体の流れをコメントで書く
セル2: データロード（動作確認）
セル3: 前処理（動作確認）
セル4: モデル定義（動作確認）
セル5: 学習ループ（動作確認）
セル6: 評価
```

各セルで「ここまでは動く」ことを確認してから次へ。

### パターン2: 実験ログ

```
セル1: 実験の目的を Markdown で記述
セル2: 設定値を明示
セル3: 実験コード
セル4: 結果の考察を Markdown で記述
セル5: 次の実験...
```

### パターン3: 使い捨てセル

```python
# 一時的なデバッグ用
# 後で削除するつもりで書く
print(type(data))
print(data.keys())
print(len(data["items"]))
```

---

## よくある落とし穴

### 1. 実行順序の罠

```python
# セルA（先に書いた）
x = 10

# セルB（後に書いた）
x = 20

# セルC
print(x)  # 10? 20? → 最後に実行したセルによる
```

**対策**: 最初から順番に実行し直す習慣

### 2. 変数名の衝突

```python
# セル1: 学習データ
data = load_train_data()

# セル2: テストデータ（上書きしてしまった！）
data = load_test_data()

# セル3: 学習（テストデータで学習してしまう）
train(data)
```

**対策**: 明確な変数名を使う (`train_data`, `test_data`)

### 3. メモリリーク

```python
# セルを何度も実行するとメモリが溜まる
model = load_huge_model()  # 毎回新しいモデルがロードされる
```

**対策**:
```python
# 明示的に解放
del model
torch.cuda.empty_cache()
```

### 4. 隠れた依存関係

```python
# セル1
from utils import helper  # このセルを実行し忘れると...

# セル2
helper()  # NameError!
```

**対策**: 必要なインポートは最初のセルにまとめる

---

## .py と .ipynb の使い分け

### .ipynb を使うべき場面

- [x] データの探索、可視化
- [x] モデルの実験、ハイパーパラメータ調整
- [x] 学習の過程を記録したい
- [x] インタラクティブに結果を確認したい
- [x] チュートリアル、学習教材

### .py を使うべき場面

- [x] プロダクションコード
- [x] ライブラリ、パッケージ
- [x] 定期実行するスクリプト
- [x] チームで共有するコード
- [x] テストを書きたい

### 組み合わせパターン

```
project/
├── notebooks/
│   ├── 01_data_exploration.ipynb   # データ探索
│   ├── 02_experiment.ipynb         # 実験
│   └── 03_evaluation.ipynb         # 評価
├── src/
│   ├── model.py                    # モデル定義（再利用）
│   ├── data.py                     # データ処理（再利用）
│   └── train.py                    # 学習スクリプト
└── scripts/
    └── run_training.sh             # 本番実行用
```

---

## Colab特有の考え方

### 1. セッションは一時的

```python
# 毎回最初に実行するセル
!pip install unsloth
from google.colab import drive
drive.mount('/content/drive')
```

### 2. GPU時間は貴重

```python
# 重い処理の前にGPUを確認
!nvidia-smi
```

### 3. Google Driveを永続ストレージとして使う

```python
# 結果はDriveに保存（セッションが切れても残る）
model.save("/content/drive/MyDrive/models/checkpoint")
```

### 4. マジックコマンドの活用

```python
%%time           # セルの実行時間を計測
%%capture        # 出力を抑制
!command         # シェルコマンド
%env VAR=value   # 環境変数設定
```

---

## 思考の切り替え方

### .py モード（設計者の思考）

```
「このコードは1年後の自分が読む」
「他の人がこのクラスを使うかもしれない」
「エラーが起きたらどうする？」
「テストはどう書く？」
```

### .ipynb モード（実験者の思考）

```
「今、この瞬間の疑問を解決する」
「動くかどうか、まず試す」
「結果を見て、次を考える」
「失敗しても、セルを書き換えればいい」
```

---

## 実践的なアドバイス

### 1. セルは小さく保つ

```
❌ 100行の巨大セル
✅ 10-20行程度の意味のある単位
```

### 2. Markdownセルで説明を入れる

```markdown
## データ前処理

ここでは以下の処理を行う：
1. 欠損値の処理
2. 正規化
3. 形式変換
```

### 3. 「動いたらコミット」の感覚

```
セル実行 → 動いた → 次のセル
           ↓
         エラー → 修正 → 再実行
```

### 4. 実験の記録を残す

```python
# 実験1: lr=1e-4, epochs=3
# 結果: loss=0.5, acc=0.8
# 考察: 過学習気味

# 実験2: lr=1e-5, epochs=5
# 結果: loss=0.3, acc=0.85
# 考察: 良好
```

---

## まとめ

```
.py  = 建築設計図（完成品を作る）
.ipynb = 実験ノート（試行錯誤を記録する）
```

両方の思考法を使い分けることで、
- 実験は .ipynb で素早く
- 本番は .py で堅牢に

という効率的な開発が可能になる。
