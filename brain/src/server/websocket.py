import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
import numpy as np

app = FastAPI()

# 起動時に一度だけロード
print("サーバー起動中...モデルロード")
stt = STTEngine()
llm = LLMEngine(2048)
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
        while True:
            # Godotから音声バイナリを受け取る（ノンブロッキング）
            # bytes -> numpy
            raw_audio = await websocket.receive_bytes()
            numpy_audio = np.frombuffer(raw_audio, dtype=np.float32) # Godotから送るデータ形式に合わせる

            # VAD判定 ＋ STT
            if stt.detect_voice(numpy_audio):
                print(".", end="", flush=True) # 喋ってる感は大事
                silence_count = 0
                audio_buffer.append(numpy_audio)
                is_recording = True

            elif is_recording:
                audio_buffer.append(numpy_audio)
                silence_count += 1
             
                if silence_count >= 10:
                    print("Finish Speech")
                    is_recording = False
                    # 音声結合
                    full_audio = np.concatenate(audio_buffer)
                    audio_buffer = [] # 使い終わったら捨てること
                    # 音声認識
                    user_text = stt.transcribe(full_audio)
                    print(f"User: {user_text}")

                    if not user_text:
                        continue

                    # 思考と発話
                    for char in llm.generate_stream(user_text):
                        audio_chunk = tts.synthesize(char)

                        if audio_chunk:
                            # synth_dataをGodotに送る
                            await websocket.send_bytes(audio_chunk)

                   

    except KeyboardInterrupt:
        print("\nGodot Disconnected")
    except Exception as e:
        print(f"Error: {e}")