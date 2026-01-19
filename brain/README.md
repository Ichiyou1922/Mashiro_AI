# brain

## Python Backend (Server)

- .venv: 開発環境(.gitignoreに入れる)

- data: 永続化データ
  - memory.lancedb/: LancdDBの実態
  - logs/: 会話ログ

- modules/: モデルファイル（.gitignoreに入れる）
  - llm/: .ggufファイル（phi-3-mini-4k-instruct.Q4_K_M.gguf）
  - stt/: Whisperモデルキャッシュ
  - tts/: VoiceVox辞書など

- src/
  - core/
    - __init__.py:
    - llm_engine.py: llama-cpp-pythonラッパー
    - stt_engine.py: faster-whisper + VAD
    - tts_engine.py: voicevox_coreラッパー
  - memory/
    - __init.py:
    - rag_store.py: LanceDB操作
  - server/
    - __init__.py:
    - websocket.py: Godotとの通信はんどら
    - schemas.py: Pydanticモデル（送受信データ定義）
  - utils/
    - audio_stream.py: 音声バッファ処理

- main.py: エントリーポイント（FastAPI app）

- run.sh: 起動スクリプト
