# TTS（Text-to-Speech）ファインチューニングガイド

## TTSの基本構造

### 現代のTTSパイプライン

```
テキスト → Encoder → 中間表現 → Decoder → 波形
                ↓
           音素変換、韻律予測、アライメント
```

### 主要なアーキテクチャ

| モデル | 特徴 | 音質 | 学習難易度 |
|--------|------|------|------------|
| **VITS** | End-to-end、高速 | ★★★★ | ★★★ |
| **StyleTTS2** | スタイル転送、自然 | ★★★★★ | ★★★★ |
| **XTTS v2** | 多言語、Voice Cloning | ★★★★ | ★★ (簡単) |
| **Tacotron2** | 古典的、安定 | ★★★ | ★★★ |
| **FastSpeech2** | 高速、並列生成 | ★★★ | ★★★ |

---

## VOICEVOXについて

### 現状

VOICEVOXはオープンソースだが、**学習用のコードは公開されていない**。

```
公開されているもの:
✅ 推論エンジン（VOICEVOX ENGINE）
✅ 学習済みの声モデル
❌ 学習用コード
❌ データセット形式の仕様（非公式情報のみ）
```

### VOICEVOXの学習は可能か？

**非常に困難**。理由：

1. **学習コード非公開**: リバースエンジニアリングが必要
2. **独自アーキテクチャ**: VITSベースだが改変あり
3. **ライセンス問題**: 商用利用に制限

### 代替案

VOICEVOXの声に近いものを作りたいなら：

1. **XTTS v2** でVoice Cloning（数秒の音声から）
2. **VITS** を自分で学習（音声データが必要）
3. **RVC** で声質変換（別アプローチ）

---

## 推奨：XTTS v2（最も簡単）

### なぜXTTSか

- **Voice Cloning**: 6秒の参照音声だけで声を模倣
- **多言語対応**: 日本語サポート
- **学習が簡単**: Coqui TTSの高レベルAPI
- **品質が高い**: 自然な抑揚

### 基本的な使い方（学習なし）

```python
from TTS.api import TTS

# モデルをロード
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

# 参照音声を使って生成（Voice Cloning）
tts.tts_to_file(
    text="こんにちは、ましろだよ",
    speaker_wav="mashiro_reference.wav",  # 6秒以上の参照音声
    language="ja",
    file_path="output.wav"
)
```

### ファインチューニング（Colab Pro推奨）

```python
# Coqui TTSの学習機能を使用
!pip install TTS

# データ準備
# 必要なもの：
# - 音声ファイル（22050Hz、mono）
# - テキストファイル（各音声の書き起こし）
```

### データ準備

```
dataset/
├── wavs/
│   ├── audio_001.wav
│   ├── audio_002.wav
│   └── ...
└── metadata.csv
```

```csv
# metadata.csv
audio_001|こんにちは、ましろだよ
audio_002|今日も配信がんばるね
audio_003|えー、それはちょっと...
```

### 学習コマンド

```bash
# XTTS v2のファインチューニング
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 \
    --config_path config.json \
    --output_path output/ \
    --train_csv dataset/metadata.csv
```

### 必要なデータ量

| データ量 | 品質 | 備考 |
|----------|------|------|
| 10分 | ★★ | 最低限 |
| 30分 | ★★★ | 実用可能 |
| 1-2時間 | ★★★★ | 推奨 |
| 5時間以上 | ★★★★★ | 最高品質 |

---

## 代替案1：VITS学習

### VITSの利点

- 完全にオープンソース
- 高品質な出力
- End-to-endで学習可能

### 環境構築（Colab）

```python
!git clone https://github.com/jaywalnut310/vits
%cd vits
!pip install -r requirements.txt
```

### データ準備

```python
# LJSpeech形式
# wavs/ フォルダに22050Hz mono音声
# metadata.csv に「ファイル名|読み|テキスト」

# 例:
# audio_001|コンニチハマシロダヨ|こんにちは、ましろだよ
```

### 前処理

```bash
# テキストの音素変換（日本語の場合）
python preprocess.py --text_index 2 --filelists filelists/mashiro_train.txt

# 学習
python train.py -c configs/mashiro.json -m mashiro_model
```

### 設定ファイルの例

```json
{
  "train": {
    "log_interval": 200,
    "eval_interval": 1000,
    "seed": 1234,
    "epochs": 10000,
    "learning_rate": 2e-4,
    "batch_size": 32
  },
  "data": {
    "training_files": "filelists/mashiro_train.txt",
    "validation_files": "filelists/mashiro_val.txt",
    "sampling_rate": 22050
  }
}
```

### 学習時間目安（A100）

- 1時間のデータ: 約6-12時間
- 30分のデータ: 約3-6時間

---

## 代替案2：RVC（声質変換）

### RVCとは

**TTS** ではなく **Voice Conversion**。

```
入力音声（任意の声） → RVC → 出力音声（ターゲットの声）
```

### 使い方

1. ましろの音声データを用意（10分程度）
2. RVCで学習
3. 任意のTTS出力をRVCで変換

```
Coqui TTS → 中間音声 → RVC → ましろの声
```

### メリット・デメリット

| メリット | デメリット |
|----------|------------|
| 少ないデータで学習可能 | リアルタイム処理に向かない |
| 簡単に声質変換 | 二段階のパイプライン |
| 品質が安定 | 元の抑揚に依存 |

---

## 実践的なロードマップ

### Phase 1: Voice Cloning（学習なし）

```python
# XTTS v2でまず試す
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

# 参照音声を数パターン用意して比較
```

**必要時間**: 数時間
**必要データ**: 6秒以上の参照音声

### Phase 2: ファインチューニング

```python
# 満足できなければXTTSをファインチューニング
# 30分程度の音声データを用意
```

**必要時間**: 1-2日（データ準備含む）
**必要データ**: 30分〜1時間の音声

### Phase 3: フルトレーニング

```python
# さらに品質を求めるならVITSをゼロから学習
```

**必要時間**: 数日〜1週間
**必要データ**: 1時間以上の音声

---

## データ収集のTips

### 良いデータの条件

```
✅ ノイズが少ない（無響室 or 近いマイク）
✅ 一定の音量
✅ 多様な表現（感情、速度のバリエーション）
✅ 正確な書き起こし
```

### データ収集方法

1. **配信アーカイブから抽出**
   - 音声部分を切り出し
   - Whisperで書き起こし
   - 手動で校正

2. **意図的な録音**
   - スクリプトを用意
   - 静かな環境で録音
   - 様々な感情で読む

3. **合成データ**
   - 既存のTTSで生成
   - 参考音声として使用（品質は下がる）

---

## Colab Proでの学習例

### セル1: 環境構築

```python
!pip install TTS
!pip install phonemizer
!apt-get install espeak-ng

import torch
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

### セル2: データ準備

```python
from google.colab import drive
drive.mount('/content/drive')

# データをDriveから読み込み
!cp -r /content/drive/MyDrive/tts_data /content/dataset
```

### セル3: 学習

```python
from TTS.api import TTS
from TTS.utils.synthesizer import Synthesizer

# XTTS v2 ファインチューニング
# 詳細は公式ドキュメント参照
```

---

## 理解のチェックポイント

- [ ] TTSの基本的なパイプライン（Text→Encoder→Decoder→Audio）を説明できる
- [ ] Voice CloningとTTS学習の違いを説明できる
- [ ] なぜVOICEVOXの学習が難しいか説明できる
- [ ] どの方法（XTTS/VITS/RVC）をどの場面で使うべきか判断できる

---

## 参考リンク

- [Coqui TTS](https://github.com/coqui-ai/TTS)
- [VITS Original](https://github.com/jaywalnut310/vits)
- [XTTS Documentation](https://docs.coqui.ai/en/latest/models/xtts.html)
- [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)
- [VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)
