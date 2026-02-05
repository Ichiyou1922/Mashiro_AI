承知しました。「車輪の再発明は避け、実用と理論のバランス重視」「C#未経験」「Live2D使用」という条件に基づき、最短距離で設計・実装・デバッグ能力を身につけるための学習ロードマップを構築しました。

すべての資料は**無料かつWeb上で閲覧可能な一次情報・高信頼なドキュメント**に限定しています。

```md
ai-agent-project/
├── .git/
├── README.md
├── docker-compose.yml       # (将来用) データベースなどをコンテナ化する場合
│
├── brain/                   # Python Backend (Server)
│   ├── .venv/               # 仮想環境 (gitignore対象)
│   ├── data/                # 永続化データ
│   │   ├── memory.lancedb/  # LanceDBの実体
│   │   └── logs/            # 会話ログ
│   ├── models/              # 重いモデルファイル (gitignore対象)
│   │   ├── llm/             # .ggufファイル (例: Phi-3-mini-4k-instruct.Q4_K_M.gguf)
│   │   ├── stt/             # Whisperモデルキャッシュ
│   │   └── tts/             # Voicevox辞書など
│   ├── src/
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── llm_engine.py    # llama-cpp-pythonラッパー
│   │   │   ├── stt_engine.py    # faster-whisper + VAD
│   │   │   └── tts_engine.py    # voicevox_coreラッパー
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── rag_store.py     # LanceDB操作
│   │   ├── server/
│   │   │   ├── __init__.py
│   │   │   ├── websocket.py     # Godotとの通信ハンドラ
│   │   │   └── schemas.py       # Pydanticモデル (送受信データ定義)
│   │   ├── utils/
│   │   │   └── audio_stream.py  # 音声バッファ処理
│   │   └── main.py              # エントリーポイント (FastAPI app)
│   ├── requirements.txt
│   └── run.sh                   # 起動スクリプト
│
└── body/                    # Godot Project (Client)
    ├── .godot/              # Godotキャッシュ
    ├── assets/              # 素材
    │   ├── models/          # 3Dモデル (VRM, GLB)
    │   ├── sounds/
    │   └── textures/
    ├── scenes/              # シーンファイル (.tscn)
    │   ├── Main.tscn
    │   └── UI.tscn
    ├── scripts/             # C# スクリプト (.cs)
    │   ├── NetworkManager.cs    # WebSocketクライアント
    │   ├── AudioManager.cs      # 音声再生・録音
    │   └── AvatarController.cs  # アニメーション制御
    ├── ai-agent-body.csproj     # C# プロジェクトファイル
    └── project.godot            # Godot設定ファイル
```

---

# AIエージェント開発学習ロードマップ (Ubuntu/GPU/Local LLM)

このロードマップは、キミが「単なるコピペ」ではなく、**「なぜ動くのか」を理解しながら、自力で機能を拡張できるエンジニア**になることを目的としています。

## Phase 1: 脳と神経の構築 (Python Backend)

**目標:** 音声を聞き分け(VAD)、テキスト化し(STT)、思考し(LLM)、発話する(TTS)サーバーを構築する。

### Step 1.1: 非同期処理とAPIサーバー (FastAPI)

Pythonでリアルタイム対話を行うには、`asyncio` の理解が不可欠です。

* **学習の核心:**
* なぜ `time.sleep()` ではなく `await asyncio.sleep()` なのか？（ブロッキングとイベントループ）
* WebSocketのライフサイクル（ハンドシェイク、メッセージ、切断）。


* **教材 (無料):**
1. **FastAPI Tutorial (公式)** - [Concurrency and async / await](https://fastapi.tiangolo.com/async/)
* *読むべき理由:* 「ハンバーガー屋」の例え話で非同期処理を直観的に解説しており、非常に分かりやすい。


2. **Python 3.x Documentation (公式)** - [Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html)
* *読むべき理由:* `async/await` の厳密な定義。FastAPIでなんとなく使った後に読むと「なるほど」となる。




* **実装課題:**
* FastAPIでWebSocketエンドポイントを作り、受け取ったテキストをそのまま送り返す（Echoサーバー）を作る。



### Step 1.2: 音声信号処理の基礎とVAD

「音」をデータとして扱うための最低限の知識です。

* **学習の核心:**
* サンプリングレート（44.1kHz vs 16kHz）とエイリアシング。
* PCMデータ（生データ）の配列表現。
* VAD（Voice Activity Detection）による「無音」と「発話」の区切り方。


* **教材 (無料):**
1. **PyAudio Documentation** - [Example: Blocking Mode Audio I/O](https://www.google.com/search?q=https://people.csail.mit.edu/hubert/pyaudio/%23docs)
* *読むべき理由:* マイクからどうやってバイト列を取り出すかの定型文。


2. **Silero VAD (GitHub)** - [README & Examples](https://github.com/snakers4/silero-vad)
* *読むべき理由:* 現在、軽量かつ最強のVAD。`torch.hub` でロードして使う方法を学ぶ。理論より「使いこなし」重視。




* **実装課題:**
* マイクに向かって喋っている間だけ録音し、無音になったらWAVファイルに保存するスクリプト。



### Step 1.3: 耳(STT)・脳(LLM)・口(TTS) の結合

ライブラリのAPIを叩くだけですが、**GPUメモリ管理**が重要です。

* **学習の核心:**
* Generator (Pythonの `yield`) を使ったストリーミング処理。
* VRAM使用量のモニタリング (`nvidia-smi`)。


* **教材 (無料):**
1. **llama-cpp-python Documentation** - [High-level API](https://llama-cpp-python.readthedocs.io/en/latest/api-reference/)
2. **Voicevox Engine API Docs** - ローカルで起動したDocker (`http://localhost:50021/docs`)
* *読むべき理由:* `audio_query` と `synthesis` の2段階プロセスを理解する。




* **実装課題:**
* マイク入力 → Whisper → LLM → Voicevox → スピーカー再生 を一気通貫で行うCLIアプリ。



---

## Phase 2: 体の構築 (Godot Engine & C#)

**目標:** C#でGodotを制御し、Pythonサーバーと通信してLive2Dモデルを動かす。

### Step 2.1: C# の基礎 (Pythonプログラマ向け)

Python/C++を知っているなら、分厚い入門書は不要です。文法差分だけを埋めます。

* **学習の核心:**
* 静的型付け (`var` と明示的型宣言)。
* クラス、プロパティ、イベント。
* `Task` と `await` (Pythonの `asyncio` と対比して理解)。


* **教材 (無料):**
1. **Microsoft Learn** - [C# の概要](https://learn.microsoft.com/ja-jp/dotnet/csharp/tour-of-csharp/)
* *読むべき理由:* 公式かつ最高品質。「プログラムの構造」「型と変数」だけざっと読めばOK。





### Step 2.2: Godot Engine の作法

Unityとは違う「ノード」と「シーン」の概念を理解します。

* **学習の核心:**
* Scene Tree (親子関係)。
* Signal (イベント駆動プログラミング)。
* Lifecycle (`_Ready`, `_Process`)。


* **教材 (無料):**
1. **Godot Docs (公式)** - [Your first 2D game](https://docs.godotengine.org/en/stable/getting_started/first_2d_game/index.html)
* *読むべき理由:* 手を動かして「Godotの流儀」を体得する最短ルート。言語設定を「C#」にして読むこと。





### Step 2.3: Live2D の導入

ここが最大の難所です。公式SDKはC++ですが、Godotには有志による拡張機能があります。

* **推奨ライブラリ:** **Godot-Cubism** (by MizunagiKB) など、GDExtension形式のプラグインを使用。
* *注意:* Live2D社公式のサポート外であることが多いため、GitHubのIssueを読む力が試されます。


* **実装課題:**
* Godot上でLive2Dモデルを表示し、パラメーター（口の開閉 `ParamMouthOpenY`）をスライダーで動かす。



### Step 2.4: WebSocket クライアントの実装

Godot (C#) から Python (FastAPI) に接続します。

* **教材 (無料):**
1. **Godot Docs** - [WebSocketPeer](https://docs.godotengine.org/en/stable/classes/class_websocketpeer.html)
* *読むべき理由:* 低レベルAPIですが、最も制御が効きます。接続状態の管理（Polling）について学ぶ。





---

## 疑問の先取りと検索ガイド (Search Strategy)

開発中に必ずぶつかるであろう壁と、その解決のための検索キーワードを用意しました。

### Q1. 「音がプツプツ途切れる / 遅延がすごい」

* **原因の推測:** バッファリング処理の不備、またはネットワーク送信の粒度が大きすぎる。
* **理論背景:** 音声は「リアルタイム性」が命。パケットが届くのを待って再生が止まる（アンダーラン）現象。
* **検索クエリ:**
* `Godot AudioStreamGeneratorPlayback C# example` (Godotで動的に音を作る方法)
* `python pyaudio chunk size latency` (適切なチャンクサイズ: 1024, 2048 etc.)
* `jitter buffer implementation` (ネットワークの揺らぎを吸収する技術)



### Q2. 「GodotでC#のパッケージ（NuGet）を使いたい」

* **原因の推測:** WebSocketライブラリなどで、標準機能より便利なものを入れたくなる。
* **解決のヒント:** Godot (.NET版) は標準の `.csproj` ファイルを使っています。
* **検索クエリ:**
* `Godot 4 .net nuget restore`
* `godot c# external library`



### Q3. 「Live2Dモデルが動かない / 表示されない」

* **原因の推測:** 読み込みパスの間違い、またはプラグインのバージョン不整合（Godot 4.x vs 3.x）。
* **解決のヒント:** Godotの「出力（Output）」タブのエラーログを必ず見る。
* **検索クエリ:**
* `godot live2d extension gdextension import error`
* `live2d cubism 5 sdk godot compatibility`



### Q4. 「AIが話し終わる前に割り込みたい（Barge-in）」

* **原因の推測:** 以前の音声再生キューが残ったまま、次の聞き取りが始まっている。
* **解決のヒント:** Python側で「ユーザーの発話検知(VAD)」シグナルを受け取ったら、Godotへ「再生停止」命令を送る。
* **検索クエリ:**
* `voice assistant barge-in implementation`
* `websocket full duplex communication architecture`



---

## 私（Gemini）へのリクエスト方法

このロードマップを進める中で、具体的なコードが必要になったり、エラーが消えない場合は、以下のように聞いてください。

* **概念がわからない時:** 「FastAPIの `async def` と `def` の使い分けについて、CPUバウンドな処理とIOバウンドな処理の観点から解説して。」
* **エラーが出た時:** エラーログを貼り付けた上で、「このエラーは、Godot側のC#のコードの問題か、Pythonサーバー側のデータ形式の問題か、切り分け方を教えて。」

まずは **Phase 1, Step 1.2（マイク入力とVAD）** から着手することをお勧めします。ここができないと、何も始まりません。

準備ができたら、「Pythonでマイク入力をリアルタイムで取得するコードを解説付きで書いて」と指示してください。