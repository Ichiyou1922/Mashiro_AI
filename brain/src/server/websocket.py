import os
import sys
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, WebSocket
from .protocol import create_state_message,create_subtitle_message, parse_client_message, create_error_message, create_done_message, create_text_response_message, create_emotion_message
import websockets
import asyncio
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from core.vad_engine import VADEngine
import struct
from memory.memory_store import UserProfileStore
from utils.text_parser import parse_emotion
from utils.tool_parser import parse_tool
from utils.tools import execute

app = FastAPI()

stt = STTEngine(model="groq")
llm = LLMEngine("llama")

tts = TTSEngine()

vad = VADEngine()

user_profile = UserProfileStore()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_queue = asyncio.Queue()
    text_queue = asyncio.Queue()

    try:
        while True:
            # 並列実行
            await asyncio.gather(
                receiver(websocket, audio_queue),
                processor(audio_queue, websocket, text_queue),
                message_send(text_queue, websocket),
                return_exceptions=True
            )

    except Exception as e:
        print(f"WebSocket disconnected: {e}")
        await websocket.close()

# 受信タスク
async def receiver(websocket: WebSocket, audio_queue: asyncio.Queue):
    """
    クライアントからのメッセージを受信してキューに振り分ける
    - バイナリ -> 音声データ -> audio_queue
    - テキスト -> JSON制御メッセージ -> 処理分岐
    """
    try:
        while True:
            # WebSocketから受信(バイナリ/テキスト)
            message = await websocket.receive()
            loop = asyncio.get_event_loop()

            if message["type"] == "websocket.receive":
                if "bytes" in message:
                    # 送信側はstruct.pack(">q", user_id) + audio_bytesとして送る
                    raw_bytes = message["bytes"]
                    user_id = struct.unpack(">q", raw_bytes[:8])[0] # 先頭8バイトを取得
                    audio_bytes = raw_bytes[8::]
                    await audio_queue.put((user_id, audio_bytes))
            
                if "text" in message:
                    msg = parse_client_message(message["text"])

                    if msg["type"] == "audio_end":
                        # processorに終了通知
                        await audio_queue.put((None, None))

                    elif msg["type"] == "text_message":
                        user_id = msg["payload"]["user_id"]
                        text = msg["payload"]["text"]
                        print("テキストを受信したよ")

                        response = await loop.run_in_executor(None, llm.generate, user_id, str(text), user_profile.get_name(user_id) or "User")
                        result = parse_tool(response)
                        if result in ["time_tool", "date_tool"]:
                            tool_result = execute(result)
                            response = await loop.run_in_executor(None, llm.generate, user_id, f"[ツール実行結果] {tool_result}", user_profile.get_name(user_id) or "User")
                        
                        print("メッセージを生成したよ")
                        clean_text, emotion = parse_emotion(response)
                        print(f"ましろemotion: {emotion}")
                        print(f"ましろtext: {clean_text}")
                        await websocket.send_text(create_emotion_message(emotion))
                        await websocket.send_text(create_text_response_message(clean_text))
                        print("Discordに流したよ")

                    elif msg["type"] == "interrupt":
                        # TODO: 割り込み処理
                        pass

                    elif msg["type"] == "cancel":
                        # TODO: キャンセル処理
                        pass
            # 切断された場合
            elif message["type"] == "websocket.disconnect":
                break

    except Exception as e:
        print(f"receiver error: {e}")
        await audio_queue.put((None, None))

# 処理タスク
async def processor(audio_queue: asyncio.Queue, websocket: WebSocket, text_queue: asyncio.Queue):
    """
    - audio_queueからbytesを取得
    - bytesをSTTにかけてtextを取得
    - textをLLMにかけて結果をtext
    """
    loop = asyncio.get_event_loop()

    try:
        while True:
            user_id, audio_data = await audio_queue.get()
            if user_id is None and audio_data is None:
                print("detect audio_end")
                continue
            else:
                await websocket.send_text(create_state_message("thinking"))
                # audio_data_silero = await loop.run_in_executor(None, vad.convert_for_whisper, audio_data)
                # text = await loop.run_in_executor(None, stt.transcribe, audio_data_silero)
                text = await loop.run_in_executor(None, stt.groq_transcribe, audio_data)

                if text is None or text.strip() == "":
                    # ハルシネーションか無音 -> スキップする
                    await websocket.send_text(create_state_message("idle"))
                    continue 

                print(f"{user_id}: {text}")
                await websocket.send_text(create_subtitle_message(f"{user_id}: {text}", True))
                generator = llm.generate_stream(user_id, str(text), user_profile.get_name(user_id) or "User")
                await loop.run_in_executor(None, producer_task_sync, generator, text_queue, loop)
                continue

    except Exception as e:
        print(f"processor error: {e}")
        await text_queue.put(None)

async def message_send(text_queue: asyncio.Queue, websocket: WebSocket):
    while True:
        data = await text_queue.get()
        try:
            if data is None:
                continue
        
            elif data["type"] == "state":
                await websocket.send_text(create_state_message(data["state"]))
                continue
            
            elif data["type"] == "text":
                audio = await tts.synthesize(data["data"])
                if audio is None:
                    await websocket.send_text(create_error_message("fault synthesize"))
                    continue
                else:
                    await websocket.send_bytes(audio)
                    continue
            
            elif data["type"] == "emotion":
                emotion = data["data"]
                print(f"emotion: {emotion}")
                if emotion is None:
                    await websocket.send_text(create_emotion_message("neutral"))
                    continue 
                else:
                    await websocket.send_text(create_emotion_message(emotion))
                    continue
            
            elif data["type"] == "done":
                await websocket.send_text(create_done_message())
                continue
        
        except Exception as e:
            print(f"audio_send error: {e}")
            await websocket.send_text(create_error_message(f"audio_send error: {e}"))
            continue

def producer_task_sync(generator, text_queue, loop):
    buffer = ''
    full_text = ''
    flag = 0
    emotion_flag = 0
    for token in generator:
        try:
            if token is None:
                if buffer:
                    loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "text", "data": buffer})
                    buffer = ''
                loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "done"})
                loop.call_soon_threadsafe(text_queue.put_nowait, None)
                break

            elif token in ["、", "。", "！", "？", "..."]:
                if buffer:
                    if flag == 0:
                        loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "state", "state": "speaking"})
                    loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "text", "data": buffer + token})
                    full_text += buffer + token
                    buffer = ''
                    flag += 1
                else:
                    print("buffer is empty")
                    continue

            elif token == '[' or emotion_flag >= 1:
                emotion_flag += 1
                if token == ']':
                    loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "emotion", "data": buffer.strip('[]')})
                    buffer = ''
                    emotion_flag = 0
                    continue
  
                buffer += token
                

            else:
                buffer += token
        except Exception as e:
            print(f"procuder_task error: {e}")
            continue
    else:
        if buffer:
            loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "text", "data": buffer})
        loop.call_soon_threadsafe(text_queue.put_nowait, {"type": "done"})
        loop.call_soon_threadsafe(text_queue.put_nowait, None)
        
