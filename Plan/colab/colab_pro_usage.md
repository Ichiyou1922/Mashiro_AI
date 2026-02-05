# Google Colab Pro 活用ガイド

## Colab Pro で得られるもの

| 項目 | 無料版 | Pro ($9.99/月) | Pro+ ($49.99/月) |
|------|--------|----------------|------------------|
| GPU | T4 (制限あり) | T4, V100, A100 | A100優先 |
| RAM | ~12GB | ~25GB High-RAM | ~52GB |
| セッション時間 | ~12時間 | ~24時間 | ~24時間 |
| バックグラウンド実行 | ❌ | ✅ | ✅ |
| ターミナル | ❌ | ✅ | ✅ |

---

## 1. Mashiro AI 開発での活用

### 1.1 合成データ生成

**目的**: 大きなモデルで高品質な会話データを自動生成

```python
# 概念的な流れ
# 1. 70Bクラスのモデルをロード（A100なら可能）
# 2. プロンプトでましろの性格を指定
# 3. 多様なシナリオで会話を生成
# 4. 品質フィルタリング
# 5. ファインチューニング用データセットとして保存
```

**実装ステップ**:
1. `unsloth/Llama-3.3-70B-Instruct` をロード（4bit量子化）
2. システムプロンプトにましろの性格定義を記述
3. 入力バリエーションを用意（雑談、哲学、ツッコミ等）
4. バッチ生成 → JSON保存
5. 人間がレビュー → 良いものだけ採用

**なぜ有効か**:
- 小さいモデルを学習させるには「教師」が必要
- 大きいモデルの出力を「蒸留」する形
- 手動でデータを作るより圧倒的に速い

---

### 1.2 複数LoRA実験

**目的**: 状況別の性格を切り替え可能にする

| LoRA名 | 特徴 | 使用場面 |
|--------|------|----------|
| mashiro_casual | 雑談、軽いノリ | 通常の会話 |
| mashiro_philosophy | 深い思考、哲学的 | 真面目な質問 |
| mashiro_tsukkomi | ツッコミ、皮肉 | ボケへの反応 |
| mashiro_ignore | 無視、興味なし | 退屈な話題 |

**実装ステップ**:
1. 各性格に特化したデータセットを用意
2. 同じベースモデルで別々にLoRA学習
3. 推論時に動的にLoRAを切り替え
4. または複数LoRAをマージ（後述）

---

### 1.3 評価・比較実験

**目的**: 最適なハイパーパラメータを見つける

```
実験例:
- r=8 vs r=16 vs r=32
- lora_alpha=16 vs lora_alpha=32
- epochs=1 vs epochs=3
- learning_rate=2e-4 vs 1e-4 vs 5e-5
```

**Colab Proの利点**:
- 長時間セッションで複数実験を連続実行
- バックグラウンド実行で放置可能

---

## 2. 学習目的での活用

### 2.1 nanoGPT実装（強く推奨）

**目的**: Transformerの仕組みを「体で」理解する

**参考資料**:
- Andrej Karpathy "Let's build GPT from scratch"
- https://github.com/karpathy/nanoGPT

**学習の流れ**:
```
1日目: Self-Attentionを手で実装
2日目: Multi-Head Attention, Feed Forward
3日目: Layer Norm, Positional Encoding
4日目: 全体を組み立てる
5日目: 実際にShakespeareで学習
6日目: 生成結果を観察、パラメータ実験
```

**なぜColab Proが必要か**:
- 実際に学習させるにはGPUが必須
- 無料版だと途中で切れる可能性
- A100なら大きめのモデルも試せる

**理解のチェックポイント**:
- [ ] Attention行列が何を表しているか説明できる
- [ ] なぜ√d_kで割るのか説明できる
- [ ] Positional Encodingがなぜ必要か説明できる
- [ ] Layer Normの位置（Pre-LN vs Post-LN）の違いを説明できる

---

### 2.2 Attention可視化

**目的**: 学習中のモデルが「何を見ているか」を観察

```python
# 概念
# 1. モデルからAttention weightを抽出
# 2. ヒートマップで可視化
# 3. 学習が進むにつれてパターンがどう変わるか観察
```

**得られる洞察**:
- 学習初期: ランダムなAttention
- 学習中期: 局所的なパターン出現
- 学習後期: 文法構造を反映したパターン

---

### 2.3 小さなLLMのフルトレーニング

**目的**: 「事前学習」とは何かを体験

```
推奨サイズ: 125M〜350Mパラメータ
データ: OpenWebText (小さいサブセット)
所要時間: A100で数時間〜1日
```

**学べること**:
- なぜ事前学習に大量のデータが必要か
- Loss曲線の意味
- 過学習 vs 汎化
- LoRAが「なぜ効率的か」の実感

---

### 2.4 Diffusion実装

**目的**: 画像生成AIの仕組みを理解

**学習の流れ**:
```
1. ノイズを加える過程（Forward process）を理解
2. ノイズを除去する過程（Reverse process）を理解
3. U-Netの役割を理解
4. MNISTで小さなDiffusionを実装
5. 生成結果を観察
```

---

## 3. 配信・実用での活用

### 3.1 Whisperファインチューニング

**目的**: 日本語認識精度向上、専門用語対応

詳細は [whisper_finetuning.md](./whisper_finetuning.md) を参照

### 3.2 TTS学習

**目的**: ましろ専用の声を作る

詳細は [tts_finetuning.md](./tts_finetuning.md) を参照

### 3.3 RAGシステム構築

**目的**: 過去の配信内容を検索可能に

```
概念:
1. 過去の配信テキストをチャンク分割
2. Embeddingモデルでベクトル化
3. ベクトルDBに保存（Chroma, FAISS等）
4. 質問に関連するチャンクを検索
5. LLMに「文脈」として渡す
```

**Colab Proの利点**:
- 大量のテキストを一括でEmbedding
- Embeddingモデル自体のファインチューニングも可能

---

## 4. 効率的な使い方のTips

### 4.1 Google Driveとの連携

```python
from google.colab import drive
drive.mount('/content/drive')

# モデルやデータをDriveに保存
# セッションが切れても継続可能
```

### 4.2 バックグラウンド実行（Pro以上）

```python
# ブラウザを閉じても実行継続
# 完了後にメール通知を設定可能
```

### 4.3 チェックポイント保存

```python
# 定期的に中間状態を保存
# クラッシュしても途中から再開可能
trainer = Trainer(
    ...
    save_strategy="steps",
    save_steps=500,
)
```

### 4.4 メモリ管理

```python
# 不要な変数を削除
del model
import gc
gc.collect()
torch.cuda.empty_cache()

# 新しいモデルをロード
```

---

## 5. 学習ロードマップ（推奨順序）

```
Week 1: nanoGPT実装
        → Transformerの基礎を完全理解

Week 2: LoRA実験
        → なぜLoRAが効率的か実感

Week 3: 合成データ生成
        → データの質が結果を左右することを理解

Week 4: 複数LoRA + マージ
        → モデルの「性格」を制御する方法を習得

Week 5: Whisper or TTS
        → 音声AIの仕組みを理解

Week 6: Diffusion（余裕があれば）
        → 画像生成AIの仕組みを理解
```

---

## 参考リンク

- [Karpathy nanoGPT](https://github.com/karpathy/nanoGPT)
- [Karpathy YouTube - Let's build GPT](https://www.youtube.com/watch?v=kCc8FmEb1nY)
- [Hugging Face PEFT](https://github.com/huggingface/peft)
- [unsloth](https://github.com/unslothai/unsloth)
- [OpenAI Whisper](https://github.com/openai/whisper)
