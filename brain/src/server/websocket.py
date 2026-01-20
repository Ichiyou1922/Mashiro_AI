from fastapi import FastAPI, WebSocket
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
import numpy as np
import queue

app = FastAPI()

stt = STTEngine()
llm = LLMEngine(2048)
tts = TTSEngine()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Godot Connected!")

    audio_buffer = []
    is_recording = False
    silence_count = 0

    audio_queue = queue.Queue()

    async def input_stream_callback(indata, frames, times, status):
        audio_queue.put(indata.copy())

    try:
        while True:
            # Godotから音声バイナリを受け取る（ノンブロッキング）
            # bytes -> numpy
            raw_audio = await websocket.receive_bytes()
            numpy_audio = np.frombuffer(raw_audio)

            if not numpy_audio:
                print("応答なし")
                continue

            # VAD判定 ＋ STT
            if stt.detect_voice(numpy_audio):
                print("Detect Speech")
                silence_count = 0
                audio_buffer.append(numpy_audio)
                is_recording = True
            elif is_recording:
                audio_buffer.append(numpy_audio)
                silence_count += 1
                print("...")
                if silence_count == 10:
                    print("Finish Speech")
                    is_recording = False
                    full_audio = np.concatenate(audio_buffer)
                    flatten_full_audio = full_audio.flatten()

                    llm_response = llm.generate_stream(flatten_full_audio)

                    for char in llm_response:
                        audio_chunk = tts.synthesize(char)
                        # synth_dataをGodotに送る
                        await websocket.send_bytes(audio_chunk)

                   

    except KeyboardInterrupt:
        print("\n終了します")