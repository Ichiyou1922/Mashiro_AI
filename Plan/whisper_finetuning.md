# Whisperファインチューニング＆ハルシネーション対策

## Whisperのハルシネーション問題

### 典型的なハルシネーションパターン

```
入力: [無音 または ノイズ]
出力: "ご視聴ありがとうございました"
      "チャンネル登録お願いします"
      "字幕：〇〇" （存在しない字幕）
```

```
入力: [短い音声]
出力: [入力と無関係な長文が生成される]
```

```
入力: [特定の言語]
出力: [別の言語で出力] または [言語が混在]
```

### なぜハルシネーションが起きるか

1. **学習データの偏り**: YouTube動画で学習 → 定型文を「学習」
2. **自己回帰の罠**: 一度間違うと連鎖的に誤る
3. **無音への対応**: 無音を「コンテンツ」として解釈
4. **Attention leak**: 関係ない部分に注目

---

## 対策1: 推論時のパラメータ調整（学習不要）

### 基本的な設定

```python
import whisper

model = whisper.load_model("large-v3")

result = model.transcribe(
    audio_path,
    language="ja",  # 言語を明示（自動検出を避ける）
    task="transcribe",

    # ハルシネーション対策
    no_speech_threshold=0.6,  # 無音判定の閾値を上げる（デフォルト0.6）
    logprob_threshold=-1.0,   # 低確信度の出力を抑制
    compression_ratio_threshold=2.4,  # 繰り返し検出

    # 温度設定
    temperature=0.0,  # 決定的な出力（ランダム性排除）

    # 条件付け
    condition_on_previous_text=False,  # 前のテキストに依存しない

    # プロンプト
    initial_prompt="日本語で話しています。",  # 言語のヒント
)
```

### パラメータ詳細

| パラメータ | 役割 | 推奨値 |
|-----------|------|--------|
| `no_speech_threshold` | 無音判定閾値 | 0.5〜0.8 |
| `logprob_threshold` | 低確信度除去 | -1.0〜-0.5 |
| `compression_ratio_threshold` | 繰り返し検出 | 2.0〜2.4 |
| `temperature` | ランダム性 | 0.0（決定的） |
| `condition_on_previous_text` | 前文脈依存 | False |

### word-level timestamps

```python
result = model.transcribe(
    audio_path,
    word_timestamps=True  # 単語レベルのタイムスタンプ
)

# セグメントごとにno_speech_probを確認
for segment in result["segments"]:
    if segment["no_speech_prob"] > 0.5:
        print(f"無音の可能性: {segment['text']}")
```

---

## 対策2: 後処理フィルタリング

### パターンマッチング（現在の方法）

```python
# ハルシネーションの典型パターン
HALLUCINATION_PATTERNS = [
    "ご視聴ありがとうございました",
    "チャンネル登録",
    "高評価",
    "字幕：",
    "字幕:",
    "（音楽）",
    "♪",
    "【",
    "】",
    # 繰り返しパターン
    r"(.+?)\1{3,}",  # 同じフレーズが3回以上
]

def filter_hallucination(text: str) -> str:
    import re

    for pattern in HALLUCINATION_PATTERNS:
        if pattern.startswith("r\""):
            # 正規表現
            text = re.sub(pattern[2:-1], "", text)
        elif pattern in text:
            return ""  # パターンを含む場合は空文字

    return text
```

### 信頼度ベースのフィルタリング

```python
def filter_by_confidence(result, threshold=0.5):
    """低信頼度のセグメントを除去"""
    filtered_segments = []

    for segment in result["segments"]:
        # no_speech確率が高い → 無音の可能性
        if segment["no_speech_prob"] > threshold:
            continue

        # avg_logprobが低い → 低信頼度
        if segment.get("avg_logprob", 0) < -1.5:
            continue

        # compression_ratioが高い → 繰り返しの可能性
        if segment.get("compression_ratio", 1) > 2.5:
            continue

        filtered_segments.append(segment)

    return filtered_segments
```

### 長さベースのフィルタリング

```python
def filter_by_length(text: str, audio_duration: float) -> str:
    """音声長に対して出力が長すぎる場合は除去"""
    # 日本語の平均発話速度: 約5〜8文字/秒
    max_chars = int(audio_duration * 10)  # 余裕を持って10文字/秒

    if len(text) > max_chars:
        return ""  # 明らかに長すぎる

    return text
```

---

## 対策3: ファインチューニング（Colab Pro）

### なぜファインチューニングか

```
問題: 汎用モデルは配信特有の語彙を知らない
解決: 配信の音声データで追加学習
```

### 期待できる効果

- [x] 専門用語の認識精度向上（ゲーム用語、コミュニティ用語）
- [x] 話者特有の発話パターンへの適応
- [x] ハルシネーション傾向の軽減（ドメイン特化により）
- [x] 言語混在問題の軽減

### 環境構築

```python
!pip install transformers datasets accelerate evaluate jiwer
!pip install bitsandbytes  # 量子化用

from transformers import WhisperProcessor, WhisperForConditionalGeneration
from transformers import Seq2SeqTrainer, Seq2SeqTrainingArguments
from datasets import load_dataset, Audio
```

### データ準備

```python
# データ形式
# audio: 音声ファイルのパス
# sentence: 正しい書き起こし

dataset = load_dataset("json", data_files={
    "train": "train.json",
    "validation": "val.json"
})

# 例: train.json
# [
#   {"audio": "path/to/audio1.wav", "sentence": "こんにちは、ましろだよ"},
#   {"audio": "path/to/audio2.wav", "sentence": "今日の配信は雑談です"},
#   ...
# ]
```

### データ前処理

```python
from transformers import WhisperProcessor

processor = WhisperProcessor.from_pretrained(
    "openai/whisper-large-v3",
    language="japanese",
    task="transcribe"
)

def prepare_dataset(batch):
    # 音声をロード
    audio = batch["audio"]

    # 特徴量抽出
    batch["input_features"] = processor(
        audio["array"],
        sampling_rate=audio["sampling_rate"],
        return_tensors="pt"
    ).input_features[0]

    # ラベル（書き起こし）をトークン化
    batch["labels"] = processor.tokenizer(
        batch["sentence"]
    ).input_ids

    return batch

# 前処理を適用
dataset = dataset.map(prepare_dataset, remove_columns=dataset.column_names["train"])
```

### 学習設定

```python
from transformers import Seq2SeqTrainingArguments

training_args = Seq2SeqTrainingArguments(
    output_dir="./whisper-mashiro",
    per_device_train_batch_size=8,
    per_device_eval_batch_size=8,
    gradient_accumulation_steps=2,
    learning_rate=1e-5,
    warmup_steps=500,
    max_steps=4000,
    gradient_checkpointing=True,  # メモリ節約
    fp16=True,  # 半精度
    evaluation_strategy="steps",
    eval_steps=1000,
    save_steps=1000,
    logging_steps=100,
    report_to="none",
    push_to_hub=False,
    predict_with_generate=True,
    generation_max_length=225,
)
```

### 学習実行

```python
from transformers import WhisperForConditionalGeneration

model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-large-v3")

# 言語・タスクを固定
model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(
    language="japanese",
    task="transcribe"
)
model.config.suppress_tokens = []

trainer = Seq2SeqTrainer(
    args=training_args,
    model=model,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    data_collator=data_collator,
    tokenizer=processor.feature_extractor,
)

trainer.train()
```

### 学習データの収集方法

```
1. 配信アーカイブから音声を切り出す
2. 既存のWhisperで書き起こし
3. 手動で校正（重要！）
4. 校正済みデータで学習

手動校正のポイント:
- ハルシネーション部分を削除
- 専門用語を正確に記述
- 句読点、表記を統一
```

### 必要なデータ量目安

| データ量 | 効果 | 備考 |
|----------|------|------|
| 1時間 | ★★ | 最低限 |
| 5時間 | ★★★ | 実用可能 |
| 10時間以上 | ★★★★ | 推奨 |

---

## 対策4: Distil-Whisper（軽量版）

### Distil-Whisperとは

大きなWhisperを「蒸留」した軽量版。

```
Whisper Large-v3: 1.5B パラメータ
Distil-Whisper:   756M パラメータ（約50%）
```

### メリット

- 高速（2-3倍）
- メモリ効率が良い
- ハルシネーションが少ない傾向（学習方法の違い）

### 使い方

```python
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

model_id = "distil-whisper/distil-large-v3"

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, torch_dtype=torch.float16, device_map="auto"
)
processor = AutoProcessor.from_pretrained(model_id)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    chunk_length_s=30,
    batch_size=16,
    return_timestamps=True,
    torch_dtype=torch.float16,
    device_map="auto",
)

result = pipe("audio.wav", generate_kwargs={"language": "japanese"})
```

---

## 対策5: faster-whisper（推論最適化）

### faster-whisperとは

CTranslate2を使った高速Whisper実装。

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")

segments, info = model.transcribe(
    "audio.wav",
    language="ja",
    vad_filter=True,  # Voice Activity Detection でハルシネーション軽減
    vad_parameters=dict(
        min_silence_duration_ms=500,  # 無音判定
        speech_pad_ms=400,
    ),
)

for segment in segments:
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
```

### VADフィルタの効果

```
VADフィルタなし:
  無音 → "ご視聴ありがとうございました"（ハルシネーション）

VADフィルタあり:
  無音 → [スキップ]（出力なし）
```

---

## 推奨アプローチの組み合わせ

### 現実的な構成

```python
class WhisperWithHallucinationFilter:
    def __init__(self):
        # faster-whisperでVADを使用
        self.model = WhisperModel("large-v3", device="cuda")

    def transcribe(self, audio_path):
        segments, _ = self.model.transcribe(
            audio_path,
            language="ja",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
        )

        results = []
        for segment in segments:
            text = segment.text

            # パターンフィルタ
            text = self.filter_patterns(text)

            # 信頼度フィルタ
            if segment.no_speech_prob > 0.5:
                continue

            if text:
                results.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": text
                })

        return results

    def filter_patterns(self, text):
        patterns = ["ご視聴", "チャンネル登録", "高評価"]
        for p in patterns:
            if p in text:
                return ""
        return text
```

---

## 理解のチェックポイント

- [ ] Whisperのハルシネーションがなぜ起きるか説明できる
- [ ] 推論パラメータ（no_speech_threshold等）の役割を説明できる
- [ ] VADフィルタがハルシネーション対策として有効な理由を説明できる
- [ ] ファインチューニングで何が改善されるか説明できる

---

## 参考リンク

- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Distil-Whisper](https://github.com/huggingface/distil-whisper)
- [HuggingFace Whisper Fine-tuning](https://huggingface.co/blog/fine-tune-whisper)
- [Whisper Hallucination研究](https://arxiv.org/abs/2401.04213)
