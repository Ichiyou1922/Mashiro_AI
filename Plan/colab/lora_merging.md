# 複数LoRAの合成・マージ手法

## 前提知識：LoRAの数学

### LoRAの基本式

```
元の重み: W (d × k)
LoRA: ΔW = A × B
      A: (d × r)  ← 低ランク
      B: (r × k)  ← 低ランク
      r << min(d, k)  ← ランク（通常8〜32）

最終的な重み: W' = W + α × (A × B)
              α = lora_alpha / r
```

**なぜこれが重要か**:
- LoRAは「加算」で適用される
- 複数のLoRAは理論上「重ね合わせ」可能
- ただし単純な加算では干渉が起きることがある

---

## 方法1: Model Merging（ベースモデルに統合）

### 概念

```
Base Model + LoRA A → Merged Model A
```

LoRAの重みをベースモデルに直接組み込む。

### 実装

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

# ベースモデルをロード
base_model = AutoModelForCausalLM.from_pretrained("base_model_name")

# LoRAを適用
model = PeftModel.from_pretrained(base_model, "path/to/lora")

# マージして新しいモデルを作成
merged_model = model.merge_and_unload()

# 保存
merged_model.save_pretrained("merged_model")
```

### メリット・デメリット

| メリット | デメリット |
|----------|------------|
| 推論時にLoRAロード不要 | 複数LoRAの切り替え不可 |
| 推論速度が速い | マージ後の編集不可 |
| シンプル | ストレージ容量大 |

---

## 方法2: LoRA Stacking（推論時に複数適用）

### 概念

```
Base Model + LoRA A + LoRA B → 推論結果
```

複数のLoRAを同時に適用する。

### 実装（HuggingFace PEFT）

```python
from peft import PeftModel

# ベースモデル
base_model = AutoModelForCausalLM.from_pretrained("base_model")

# 最初のLoRAを適用
model = PeftModel.from_pretrained(base_model, "path/to/lora_a", adapter_name="lora_a")

# 2つ目のLoRAを追加
model.load_adapter("path/to/lora_b", adapter_name="lora_b")

# 両方を有効化（重み付け）
model.set_adapter(["lora_a", "lora_b"])
```

### 重み付けマージ

```python
# 各LoRAの影響度を調整
model.add_weighted_adapter(
    adapters=["lora_a", "lora_b"],
    weights=[0.7, 0.3],  # lora_a: 70%, lora_b: 30%
    adapter_name="merged"
)
```

### メリット・デメリット

| メリット | デメリット |
|----------|------------|
| 動的に切り替え可能 | 推論時のオーバーヘッド |
| 重み調整が容易 | メモリ使用量増加 |
| 実験しやすい | 干渉の可能性 |

---

## 方法3: Linear Merge（線形補間）

### 概念

```
LoRA_merged = α × LoRA_A + β × LoRA_B
```

複数のLoRAの重みを直接足し合わせる。

### 実装

```python
import torch

def merge_loras(lora_a_path, lora_b_path, alpha=0.5, beta=0.5):
    """
    2つのLoRAを線形結合してマージ
    """
    # LoRAの状態をロード
    lora_a = torch.load(f"{lora_a_path}/adapter_model.bin")
    lora_b = torch.load(f"{lora_b_path}/adapter_model.bin")

    merged = {}
    for key in lora_a.keys():
        if key in lora_b:
            # 同じキーは重み付け平均
            merged[key] = alpha * lora_a[key] + beta * lora_b[key]
        else:
            merged[key] = lora_a[key]

    # lora_bにしかないキーも追加
    for key in lora_b.keys():
        if key not in merged:
            merged[key] = lora_b[key]

    return merged
```

### 注意点

- `alpha + beta = 1` である必要はない
- `alpha + beta > 1` で効果を強める
- `alpha + beta < 1` で効果を弱める

---

## 方法4: TIES-Merging（高度な手法）

### 概念

複数のモデル/LoRAを「タスク干渉」を最小化してマージ。

```
1. 各LoRAで変化が大きい重みを特定
2. 符号が一致する重みだけを残す
3. 平均化してマージ
```

### なぜ有効か

- 単純な平均だと、異なるタスクの重みが打ち消し合う
- TIES-Mergingは「重要な」重みを保護

### 実装（mergekit使用）

```yaml
# mergekit config
merge_method: ties
base_model: base_model_name
models:
  - model: lora_a
    parameters:
      weight: 0.5
      density: 0.5
  - model: lora_b
    parameters:
      weight: 0.5
      density: 0.5
```

```bash
# mergekitでマージ実行
mergekit-yaml config.yaml output_path
```

---

## 方法5: DARE-Merging

### 概念

TIESの改良版。ランダムに重みを「ドロップ」してから再スケール。

```
1. 各LoRAの重みをランダムに一部削除（dropout的）
2. 削除率に応じて残った重みを拡大
3. マージ
```

### メリット

- ノイズが減る
- より安定したマージ結果

---

## 実践的な使い分け

### Mashiro AIでの活用例

```
LoRA構成:
├── mashiro_base      # 基本的な性格
├── mashiro_casual    # 雑談特化
├── mashiro_serious   # 真面目な話題
└── mashiro_ignore    # 興味なし反応
```

### シナリオ1: 固定的な性格

```python
# 事前にマージして一つのLoRAにする
merged = merge_loras(
    "mashiro_base",
    "mashiro_casual",
    alpha=0.7,
    beta=0.3
)
# このマージ済みLoRAを使用
```

### シナリオ2: 動的な性格切り替え

```python
# 話題に応じてLoRAを切り替え
if topic_is_casual:
    model.set_adapter("mashiro_casual")
elif topic_is_serious:
    model.set_adapter("mashiro_serious")
elif topic_is_boring:
    model.set_adapter("mashiro_ignore")
```

### シナリオ3: 段階的な性格変化

```python
# 時間帯や状況に応じて重みを変える
morning_weights = {"casual": 0.8, "serious": 0.2}
night_weights = {"casual": 0.3, "serious": 0.7}

model.add_weighted_adapter(
    adapters=["mashiro_casual", "mashiro_serious"],
    weights=[0.8, 0.2],  # 朝は軽いノリ
    adapter_name="current"
)
```

---

## 実装手順（Colabでの例）

### Step 1: 複数のLoRAを学習

```python
# 同じベースモデルで、異なるデータセットでLoRAを学習
# データセット1: 雑談データ → mashiro_casual
# データセット2: 真面目データ → mashiro_serious
```

### Step 2: マージを試す

```python
from peft import PeftModel, PeftConfig

# ベースモデル
base = AutoModelForCausalLM.from_pretrained("base_model")

# 最初のLoRA
model = PeftModel.from_pretrained(base, "mashiro_casual", adapter_name="casual")

# 2つ目のLoRA
model.load_adapter("mashiro_serious", adapter_name="serious")

# 重み付けマージを試す
for alpha in [0.3, 0.5, 0.7]:
    model.add_weighted_adapter(
        adapters=["casual", "serious"],
        weights=[alpha, 1-alpha],
        adapter_name=f"merged_{alpha}"
    )
    # テスト
    model.set_adapter(f"merged_{alpha}")
    output = generate(model, "こんにちは")
    print(f"alpha={alpha}: {output}")
```

### Step 3: 最適な重みを見つけたらマージ

```python
# 最適な重みでマージ
final_model = model.merge_and_unload()
final_model.save_pretrained("mashiro_final")
```

---

## よくある問題と対策

### 1. 性格が混ざって中途半端に

```
原因: 相反するデータでLoRAを学習
対策: データの方向性を統一、または重みを極端に（0.9:0.1等）
```

### 2. どちらのLoRAの効果も弱い

```
原因: 重みの打ち消し合い
対策: TIES/DAREを使う、または片方のrankを上げる
```

### 3. 特定のタスクで性能が落ちる

```
原因: タスク間の干渉
対策: 動的切り替え（マージではなく）を検討
```

---

## ツール紹介

### mergekit

```bash
pip install mergekit
```

様々なマージ手法を試せるCLIツール。

### PEFT

```python
from peft import PeftModel
```

HuggingFaceの公式LoRAライブラリ。マージ機能内蔵。

### unsloth

マージ後のモデルをGGUFに変換する場合に便利。

---

## 理解のチェックポイント

- [ ] なぜLoRAは「加算」で適用できるのか説明できる
- [ ] 線形マージと動的切り替えの違いを説明できる
- [ ] TIES-Mergingがなぜ単純平均より良いのか説明できる
- [ ] どの場面でどのマージ方法を使うべきか判断できる

---

## 参考リンク

- [PEFT Documentation](https://huggingface.co/docs/peft)
- [mergekit](https://github.com/arcee-ai/mergekit)
- [TIES-Merging Paper](https://arxiv.org/abs/2306.01708)
- [DARE Paper](https://arxiv.org/abs/2311.03099)
