import os
import sys
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, WebSocket
from .protocol import create_state_message,create_subtitle_message, parse_client_message, create_error_message, create_done_message, create_text_response_message, create_emotion_message, create_autonomous_message, create_volume_message, create_action_message, create_finish_message
import websockets
import asyncio
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from core.vad_engine import VADEngine
import struct
from memory.memory_store import UserProfileStore, memory_store
from utils.tools import execute, vision_tool
from memory.reflection import ReflectionManager
import re
import time
from collections import deque
from typing import List, AsyncGenerator
import json


app = FastAPI()
stt = STTEngine(model="groq")
llm = LLMEngine()
# 'voicevox' or 'qwen' or 'azure'
tts = TTSEngine(backend='voicevox')
vad = VADEngine()
user_profile = UserProfileStore()
reflection = ReflectionManager()
importance_counter = 0
last_interaction_time = 0.0
ignore_counter = 0
ai_state = "idle"
godot_queue: asyncio.Queue | None = None
voice_text_queue: asyncio.Queue | None = None
interrupt_event: asyncio.Event | None = None
lock = asyncio.Lock()
discord_command_queue: asyncio.Queue | None = None

@app.websocket("/ws/voice")
async def voice_endpoint(websocket: WebSocket):
    await websocket.accept()
    global voice_text_queue
    global interrupt_event
    audio_queue = asyncio.Queue()
    text_queue = asyncio.Queue()
    interrupt_event = asyncio.Event()
    voice_text_queue = text_queue


    try:
        while True:
            # 並列実行
            await asyncio.gather(
                audio_receiver(websocket, audio_queue),
                processor(audio_queue, websocket, text_queue),
                message_send(text_queue, websocket),
                autonomy_loop(websocket, text_queue),
                return_exceptions=True
            )

    except Exception as e:
        print(f"audio_endpoint disconnected: {e}")
        await websocket.close()
    
    finally:
        voice_text_queue = None

@app.websocket("/ws/text")
async def text_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.gather(
                text_receiver(websocket),
                reflection_timer(websocket),
                return_exceptions=True
            )

    except Exception as e:
        print(f"text_endpoint disconnected: {e}")
        await websocket.close()

@app.websocket("/ws/godot")
async def godot_endpoint(websocket: WebSocket):
    await websocket.accept()
    global godot_queue
    try:
        godot_queue = asyncio.Queue()
        while True:
            data = await godot_queue.get()
            if data is None:
                await asyncio.sleep(0.1)
                continue
            elif data["type"] == "state":
                await websocket.send_text(create_state_message(data["state"]))
                continue
            elif data["type"] == "text":
                await websocket.send_text(create_text_response_message(data["data"]))
                continue
            elif data["type"] == "volume":
                await websocket.send_text(create_volume_message(data["volume"]))
            elif data["type"] == "emotion":
                emotion = data["data"]
                if emotion is None:
                    await websocket.send_text(create_emotion_message("neutral"))
                    continue
                else:
                    await websocket.send_text(create_emotion_message(emotion))
                    continue

    except Exception as e:
        print(f"godot_endpoint disconnected: {e}")
        godot_queue = None

@app.websocket("/ws/game")
async def game_endpoint(websocket: WebSocket):
    await websocket.accept()
    global voice_text_queue
    global lock
    loop = asyncio.get_event_loop()
    game_memory = deque(maxlen=16)
    game_rules = ""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive" and "text" in message:
                msg = parse_client_message(message["text"])
                if msg["type"] == "game_start":
                    game_name = msg["payload"]["game_name"]
                    game_rules = msg["payload"]["rules"]
                elif msg["type"] == "context":
                    context = msg["payload"]["context"]
                    action_request = msg["payload"]["action_request"]
                    if action_request:
                        game_memory.append({"role": "user", "content": context})
                        # game_memory.append({"role": "user", "content": action_request})
                        result = {}
                        max_retry = 3
                        retry_count = 0
                        while result == {} and retry_count < max_retry:
                            async with lock:
                                result = await loop.run_in_executor(None, llm.generate_game_action, context, action_request, list(game_memory), game_rules)
                            retry_count += 1
                        if result == {}:
                            await websocket.send_text(create_error_message("fault create action"))
                            # pywright側で停止
                            break
                        if result["action"]:
                            # 仮置き
                            text = result["text"]
                            if voice_text_queue:
                                await voice_text_queue.put({"type": "state", "state": "speaking"})
                                await voice_text_queue.put({"type": "text", "data": text})
                                await voice_text_queue.put({"type": "done"})
                            memory_store.short_term.append({"role": "assistant_message", "text": text, "user_name": "ましろ", "timestamp": time.time(), "importance": 0})
                            action = result["action"]
                            game_memory.append({"role": "assistant", "content": text + action})
                            await websocket.send_text(create_action_message(action))
                        else:
                            # actionが無いならただの会話である
                            text = result["text"]
                            if voice_text_queue:
                                await voice_text_queue.put({"type": "state", "state": "speaking"})
                                await voice_text_queue.put({"type": "text", "data": text})
                                await voice_text_queue.put({"type": "done"})
                            memory_store.short_term.append({"role": "assistant_message", "text": text, "user_name": "ましろ", "timestamp": time.time(), "importance": 0})
                            game_memory.append({"role": "assistant", "content": text})
                            
                    else:
                        game_memory.append({"role": "user", "content": context})
                    
                elif msg["type"] == "action_result":
                    action_result = msg["payload"]["action_result"]
                    game_memory.append({"role": "user", "content": action_result})
    except Exception as e:
        print(f"game_endpoint disconnected: {e}")

async def _get_final_response(text: str, user_id: int, image_url: str | None = None) -> AsyncGenerator[dict, None]:
    global importance_counter
    loop = asyncio.get_event_loop()
    if image_url:
        vision_text = await loop.run_in_executor(None, vision_tool.analyze_image, image_url)
        text = f"{text} [画像の説明]: {vision_text}"

    print(f"{user_profile.get_name(user_id)}: {text}")
    async with lock:
        result = await loop.run_in_executor(None, llm.generate, user_id, str(text), user_profile.get_name(user_id) or "User")
        if result == {}:
            max_retry = 3
            retry_count = 0
            while result == {} and retry_count < max_retry:
                print("再生成を試みます...")
                result = await loop.run_in_executor(None, llm.generate, user_id, str(text), user_profile.get_name(user_id) or "User")
                retry_count += 1
                if result != {}:
                    print("再生成成功")
                    break

    importance_counter += 1
    if importance_counter >= 20:
        asyncio.ensure_future(loop.run_in_executor(None, memory_store.evaluate_importance))
        importance_counter = 0

    if result.get("function") and result["function"]["tool_name"] in [
        "time_tool", "date_tool", "search_tool",
        "send_discord_message", "join_voice", "leave_voice"
        ]:
        if result.get("text") is None or result["text"].strip() == "":
             result["text"] = f"{result['function']['tool_name']}実行中..."
 
        yield {
            "text": result["text"],
            "emotion": result.get("emotion", "neutral"),
            "speaking_rate": result.get("speaking_rate", 1.0),
            "function": None
        }
        tool_name = result["function"]["tool_name"]
        param = result["function"].get("param", None)
        tool_result = execute(tool_name, param)
        memory_store.short_term.append({"text": tool_result, "role": "tool_result", "user_name": "system", "timestamp": time.time()})
        print(tool_result)
        include_tool_text = {
            "mashiro_function_calling": json.dumps(result, ensure_ascii=False),
            "tool_result": tool_result
        }
        async with lock:
            result = await loop.run_in_executor(None, llm.generate, user_id, str(text), user_profile.get_name(user_id) or "User", False, include_tool_text)
            if result == {}:
                max_retry = 3
                retry_count = 0
                while result == {} and retry_count < max_retry:
                    print("再生成を試みます...")
                    result = await loop.run_in_executor(None, llm.generate, user_id, str(text), user_profile.get_name(user_id) or "User", False, include_tool_text)
                    retry_count += 1
                    if result != {}:
                        print("再生成成功")
                        break
    if result == {} or result.get("text") is None or result["text"].strip() == "":
        result = {
            "text": "応答エラーが発生しました。原因を調査してください。",
            "emotion": "neutral",
            "speaking_rate": 1.0,
            "think": "",
            "function": None
        }
    
    yield result

async def reflection_timer(websocket: WebSocket):
    loop = asyncio.get_event_loop()    
    while True:
        await asyncio.sleep(1800)
        importance_sum = memory_store.get_importance_sum(since=reflection.last_reflection_at)
        if reflection.check_and_trigger(importance_sum) is False:
            continue
        await websocket.send_text(create_state_message("sleeping"))
        await loop.run_in_executor(None, reflection.perform_reflection)
        await websocket.send_text(create_state_message("idle"))

async def autonomy_loop(websocket: WebSocket, text_queue: asyncio.Queue):
    """
    中枢神経ループ 今の所沈黙を検知して発火
    今後追加予定
    - social
    - boredom
    - energy
    - ???
    """
    global last_interaction_time
    last_interaction_time = time.time()

    global ignore_counter
    global ai_state
    global godot_queue
    global importance_counter

    boredom_threshold = 30.0
    check_interval = 1.0

    print("Autonomy Loop Started.")

    while True:
        if ai_state == "idle":
            await asyncio.sleep(check_interval)

            current_time = time.time()
            silence_duration = current_time - last_interaction_time

            if silence_duration > boredom_threshold:
                ignore_counter += 1
                print(f"Autonomy Triggered: Silence for {silence_duration:.1f}s")

                last_interaction_time = time.time()

                await websocket.send_text(create_state_message("thinking"))
                ai_state = "thinking"
                if godot_queue is not None:
                    await godot_queue.put({"type": "state", "state": "thinking"})

                loop = asyncio.get_event_loop()
                implus = f"ユーザーからの返事がありません。{silence_duration:.0f}秒間沈黙が続いています（自発的な試み{ignore_counter}回目）。直近の会話を読み返し補足や配慮が必要なら話してください。ツールを使うこともできます。話すべきなら返答を、話さないなら「...」を出力してください。"
                async with lock:
                    result = await loop.run_in_executor(None, llm.generate_autonomous, implus, None)
                    if result == {}:
                        max_retry = 3
                        retry_count = 0
                        while result == {} and retry_count < max_retry:
                            print("再生成を試みます...")
                            result = await loop.run_in_executor(None, llm.generate_autonomous, implus, None)
                            retry_count += 1
                            if result != {}:
                                print("再生成成功")
                                break

                importance_counter += 1
                if importance_counter >= 20:
                    asyncio.ensure_future(loop.run_in_executor(None, memory_store.evaluate_importance))
                    importance_counter = 0

                if result.get("function") and result["function"]["tool_name"] in [
                    "time_tool", "date_tool", "search_tool",
                    "send_discord_message", "join_voice", "leave_voice"
                    ]:
                    tool_name = result["function"]["tool_name"]
                    param = result["function"].get("param", None)
                    if result.get("text") is None or result["text"].strip() == "":
                        result["text"] = f"{result['function']['tool_name']}実行中..."
                    result = {
                        "text": result["text"],
                        "emotion": result.get("emotion", "neutral"),
                        "speaking_rate": result.get("speaking_rate", 1.0),
                        "function": None
                    }
                    await text_queue.put({"type": "state", "state": "speaking"})
                    ai_state = "speaking"
                    await text_queue.put({"type": "emotion", "data": result["emotion"]})
                    if godot_queue is not None:
                        await godot_queue.put({"type": "emotion", "data": result["emotion"]})
                    print(f"ましろemotion: {result['emotion']}")
                    print(f"ましろtext: {result['text']}")
                    print("Discordに流したよ")
                    parsed_result = re.split(r'([、。？！…]|\.{3}|\.{6})', result["text"])
                    for text in parsed_result:
                        if text.strip():
                            await text_queue.put({"type": "text", "data": text, "speaking_rate": result["speaking_rate"]})
                            if godot_queue is not None:
                                await godot_queue.put({"type": "text", "data": text})
                    await text_queue.put({"type": "done"})
                    tool_result = execute(tool_name, param)
                    print(f"Autonomous Tool Result: {tool_result}")
                    context_for_2nd = {**result, "function": None}
                    include_tool_text = {
                        "mashiro_function_calling": json.dumps(context_for_2nd, ensure_ascii=False),
                        "tool_result": tool_result
                    }
                    async with lock:
                        result = await loop.run_in_executor(None, llm.generate_autonomous, implus, include_tool_text)
                        if result == {}:
                            max_retry = 3
                            retry_count = 0
                            while result == {} and retry_count < max_retry:
                                print("再生成を試みます...")
                                result = await loop.run_in_executor(None, llm.generate_autonomous, implus, include_tool_text)
                                retry_count += 1
                                if result != {}:
                                    print("再生成成功")
                                    break
                if result == {} or result.get("text") is None or result["text"].strip() == "":
                    result = {
                        "text": "応答エラーが発生しました。原因を調査してください。",
                        "emotion": "neutral",
                        "speaking_rate": 1.0,
                        "think": "",
                        "function": None
                    }

                if result["text"].startswith("...") or result["text"].startswith("…"):
                    # print("ましろは喋らない選択をしました。")
                    await websocket.send_text(create_state_message("idle"))
                    ai_state = "idle"
                    if godot_queue is not None:
                        await godot_queue.put({"type": "state", "state": "idle"})
                    continue

                await text_queue.put({"type": "state", "state": "speaking"})
                ai_state = "speaking"

                # もはやtext_queueにemotionは必要無いかも
                await text_queue.put({"type": "emotion", "data": result["emotion"]})
                if godot_queue is not None:
                    await godot_queue.put({"type": "emotion", "data": result["emotion"]})
                print(f"ましろemotion: {result['emotion']}")
                print(f"ましろtext: {result['text']}")
                print("Discordに流したよ")

                parsed_result = re.split(r'([、。？！…]|\.{3}|\.{6})', result["text"])
                for text in parsed_result:
                    if text.strip():
                        await text_queue.put({"type": "text", "data": text, "speaking_rate": result["speaking_rate"]})
                        if godot_queue is not None:
                            await godot_queue.put({"type": "text", "data": text})

                await text_queue.put({"type": "done"})
                continue
        else:
            # print("自己発話プロセスをスキップしました。")
            await asyncio.sleep(check_interval / 10.0)
            last_interaction_time = time.time()

async def text_receiver(websocket: WebSocket):
    """クライアントからメッセージを受信して生成テキストを送り返す"""
    global importance_counter
    loop = asyncio.get_event_loop()
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.receive" and "text" in message:
                msg = parse_client_message(message["text"])
                if msg["type"] == "text_message":
                    user_id = msg["payload"]["user_id"]
                    text = msg["payload"]["text"]
                    image_url = msg["payload"].get("image_url")
                    print("textを受信したよ")

                    async for result in _get_final_response(text, user_id, image_url):
                        if result.get("text") is None or result["text"].strip() == "":
                            result["text"] = "応答エラーが発生しました。原因を調査してください。"
                        if result.get("emotion") is None:
                            result["emotion"] = "neutral"
                        if result.get("speaking_rate") is None:
                            result["speaking_rate"] = 1.0

                        print("メッセージを生成したよ")
                        print(f"ましろemotion: {result['emotion']}")
                        print(f"ましろtext: {result['text']}")
                        await websocket.send_text(create_emotion_message(result["emotion"]))
                        await websocket.send_text(create_text_response_message(result["text"]))
                        print("Discordに流したよ")
                    await websocket.send_text(create_finish_message())
    except Exception as e:
        print(f"text_receiver error: {e}")
                

# 受信タスク
async def audio_receiver(websocket: WebSocket, audio_queue: asyncio.Queue):
    """
    クライアントからのメッセージを受信してキューに振り分ける
    - バイナリ -> 音声データ -> audio_queue
    - テキスト -> JSON制御メッセージ -> 処理分岐
    """
    global importance_counter
    global last_interaction_time
    global ignore_counter
    global interrupt_event

    try:
        while True:
            # WebSocketから受信(バイナリ/テキスト)
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                if "bytes" in message:
                    ignore_counter = 0
                    last_interaction_time = time.time()
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

                    elif msg["type"] == "interrupt":
                        if interrupt_event is not None:
                            print("interrupt_event set")
                            interrupt_event.set()

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
    global importance_counter
    global ai_state
    global godot_queue

    try:
        while True:
            user_id, audio_data = await audio_queue.get()
            if user_id is None and audio_data is None:
                print("detect audio_end")
                continue
            else:
                await websocket.send_text(create_state_message("thinking"))
                ai_state = "thinking"
                if godot_queue is not None:
                    await godot_queue.put({"type": "state", "state": "thinking"})
                # audio_data_silero = await loop.run_in_executor(None, vad.convert_for_whisper, audio_data)
                # text = await loop.run_in_executor(None, stt.transcribe, audio_data_silero)
                text = await loop.run_in_executor(None, stt.groq_transcribe, audio_data)

                if text is None or text.strip() == "":
                    # ハルシネーションか無音 -> スキップする
                    await websocket.send_text(create_state_message("idle"))
                    ai_state = "idle"
                    if godot_queue is not None:
                        await godot_queue.put({"type": "state", "state": "idle"})
                    continue 

                await websocket.send_text(create_subtitle_message(f"{user_id}: {text}", True))

                async for result in _get_final_response(text, user_id):
                    if result.get("text") is None or result["text"].strip() == "":
                        result["text"] = "応答エラーが発生しました。原因を調査してください。"
                    if result.get("emotion") is None:
                        result["emotion"] = "neutral"
                    if result.get("speaking_rate") is None:
                        result["speaking_rate"] = 1.0
                            
                    print("メッセージを生成したよ")
                    # 句点で分割し、区切り文字を前のセグメントに結合する
                    # 例: "こんにちは。元気？" → ["こんにちは。", "元気？"]
                    raw_split = re.split(r'([。？！…])', result["text"])
                    parsed_result = []
                    for i in range(0, len(raw_split), 2):
                        chunk = raw_split[i]
                        if i + 1 < len(raw_split):
                            chunk += raw_split[i + 1]
                        if chunk.strip():
                            parsed_result.append(chunk)
                    
                    # Speaking状態を開始
                    await text_queue.put({"type": "state", "state": "speaking"})
                    ai_state = "speaking"

                    await text_queue.put({"type": "emotion", "data": result["emotion"]})
                    if godot_queue is not None:
                        await godot_queue.put({"type": "emotion", "data": result["emotion"]})
                    for text in parsed_result:
                        if text.strip():
                            await text_queue.put({"type": "text", "data": text, "speaking_rate": result["speaking_rate"]})
                            if godot_queue is not None:
                                await godot_queue.put({"type": "text", "data": text})
                            
                    await text_queue.put({"type": "done"})
                    continue

    except Exception as e:
        print(f"processor error: {e}")
        await text_queue.put(None)

async def message_send(text_queue: asyncio.Queue, websocket: WebSocket):
    global ai_state
    global godot_queue
    spoken_chunks = []
    while True:
        # data = await text_queue.get()
        get_task = asyncio.create_task(text_queue.get())
        if interrupt_event:
            int_task = asyncio.create_task(interrupt_event.wait())

            done, pending = await asyncio.wait(
                [get_task, int_task],
                return_when=asyncio.FIRST_COMPLETED
            )
        else:
            done, pending = await asyncio.wait(
                [get_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            int_task = None

        for t in pending:
            t.cancel()

        try:
            if int_task and int_task in done:
                print("websocket interrupt detected")
                ai_state = "idle"
                await websocket.send_text(create_state_message("idle"))
                # llm_engine.generate内のadd_memoryで保存済み（二重保存防止）
                # response = "".join(spoken_chunks)
                # memory_store.short_term.append({"text": response, "role": "assistant_message", "user_name": "ましろ", "timestamp": time.time()})
                while not text_queue.empty():
                    text_queue.get_nowait()
                if interrupt_event:
                    interrupt_event.clear()
                spoken_chunks = []
            else:
                data = get_task.result()
                if data is None:
                    continue
            
                elif data["type"] == "state":
                    await websocket.send_text(create_state_message(data["state"]))
                    continue
                
                elif data["type"] == "text":
                    # audio = await tts.synthesize(data["data"])
                    if tts.backend == 'voicevox':
                        audio = await tts.synthesize(data["data"], speaking_rate=float(data.get("speaking_rate", 1.0)))
                    elif tts.backend == 'qwen':
                        audio = await asyncio.to_thread(tts.qwen_synthesize, data["data"])
                    elif tts.backend == 'azure':
                        audio = await asyncio.to_thread(tts.azure_synthesize, data["data"])

                    if audio is None:
                        await websocket.send_text(create_error_message("fault synthesize"))
                        continue
                    else:
                        await websocket.send_bytes(audio)
                        spoken_chunks.append(data["data"])
                        continue
                
                elif data["type"] == "emotion":
                    emotion = data["data"]
                    if emotion is None:
                        await websocket.send_text(create_emotion_message("neutral"))
                        continue 
                    else:
                        await websocket.send_text(create_emotion_message(emotion))
                        continue
                
                elif data["type"] == "done":
                    await websocket.send_text(create_done_message())
                    # llm_engine.generate内のadd_memoryで保存済み（二重保存防止）
                    # response = "".join(spoken_chunks)
                    # memory_store.short_term.append({"text": response, "role": "assistant_message", "user_name": "ましろ", "timestamp": time.time()})
                    ai_state = "idle"
                    spoken_chunks = []
                    continue
        
        except Exception as e:
            print(f"audio_send error: {e}")
            await websocket.send_text(create_error_message(f"audio_send error: {e}"))
            continue
