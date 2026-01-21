import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
import numpy as np
import asyncio

app = FastAPI()

# 起動時に一度だけロード
print("サーバー起動中...モデルロード")
stt = STTEngine()
llm = LLMEngine(4096)
tts = TTSEngine()
print("モデルロード完了")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Godot Connected!")

    audio_buffer = []
    is_recording = False
    silence_count = 0

    try:
        while True: await asyncio.sleep(1)
            

                   

    except KeyboardInterrupt:
        print("\nGodot Disconnected")
    except Exception as e:
        print(f"Error: {e}")