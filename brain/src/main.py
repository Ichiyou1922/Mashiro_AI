import discord
from core.vad_engine import VADEngine
from memory.memory_store import UserProfileStore
from discord.ext import commands
from discord.ext import voice_recv
from dotenv import load_dotenv
import os
import asyncio
import torch
import time
import io
import logging
import uvicorn
import server.websocket as fastapi
import websockets
import struct
from server.protocol import parse_client_message, create_state_message, create_text_message
import json
import re

logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.WARNING)
os.environ["AV_LOG_LEVEL"] = "quiet"

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
reconnect_enabled = True  # 再接続フラグ。

profile = UserProfileStore()

text_response_queue = asyncio.Queue()


# def remove_thoughts(text: str) -> str:
#     pattern = r"\（思考:.*?\）"
#     cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
#     return cleaned_text.strip()

def remove_thoughts(text: str) -> str:
    pattern = r"<think>.*?</think>"
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
    return cleaned_text.strip()

# ========== AudioSink ==========
class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, vc, ws):
        print("MyAudioSink __init__ 開始")
        super().__init__()
        self.vad = VADEngine()

        self.ev_loop = bot.loop

        # ユーザーごとの音声バッファ
        self.user_data = {}

        # バックグラウンドタスク
        self.bg_task = self.ev_loop.create_task(self.check_silence_loop())
        self.queue_task = self.ev_loop.create_task(self.process_queue_loop())

        # 音声再生用
        self.vc = vc

        # Processing中フラグ
        self.is_processing = False

        # オーディオキュー
        self.audio_queue = asyncio.Queue()

        # websocket
        self.ws = ws

        # AIの状態
        self.ai_state = "idle" # idle / listening / speaking

        print("MyAudioSink __init__ 完了")

    def wants_opus(self) -> bool:
        return False

    async def process_queue_loop(self):
        """キューから音声データを取り出して順番に処理するワーカー"""
        print("process_queue started")
        while True:
            user, user_key, audio_bytes = await self.audio_queue.get()
            await self.process_conversation(user_key, audio_bytes)

    async def check_silence_loop(self):
        print("Watchdog started.")
        while True:
            await asyncio.sleep(0.1)

            # Processing中はスキップ
            if self.is_processing or self.ai_state == "speaking":
                for key in list(self.user_data.keys()):
                    self.user_data[key]["buffer"].clear()
                    self.user_data[key]["is_speaking"] = False
                continue

            current_time = time.time()
            for user_key in list(self.user_data.keys()):

                # 喋り中でなければスキップ
                if not self.user_data[user_key]["is_speaking"]:
                    continue

                # 最後のパケットから0.5秒以上経過してる？
                silence_duration = current_time - self.user_data[user_key]["last_seen"]

                if silence_duration > 0.5:
                    self.is_processing = True

                    print(f"\nFlash! (Silence: {silence_duration:.2f}s)")

                    # Flash処理
                    self.user_data[user_key]["is_speaking"] = False
                    self.user_data[user_key]["tick"] = 0
                    self.user_data[user_key]["small_buffer"] = []

                    # バッファが有るなら処理
                    if self.user_data[user_key]["buffer"]:
                        full_audio_bytes = b"".join(self.user_data[user_key]["buffer"])
                        self.user_data[user_key]["buffer"].clear()
                        user = self.user_data[user_key]["user"]

                        await self.audio_queue.put((user, user_key, full_audio_bytes))

    def write(self, user, data) -> None:
        try:
            if self.ai_state == "speaking":
                return
            # ユーザーが特定できないパケットは無視
            if user is None or user.bot:
                return

            # Processing中は新しい音声を受け付けない
            if self.is_processing:
                return

            # data.pcmは bytes型のPCMデータ
            if not hasattr(data, 'pcm'):
                print(f"Error: Data has no .pcm attribute. Type: {type(data)}")
                return

            user_key = str(user.id)
            current_time = time.time()

            # 初期化
            if user_key not in self.user_data:
                self.user_data[user_key] = {
                    "buffer": [],
                    "small_buffer": [],
                    "tick": 0,
                    "is_speaking": False,
                    "last_seen": current_time,
                    "user": user  # userオブジェクトを保存
                }

            # パケット受信のたびにlast_seenとuserを更新
            self.user_data[user_key]["last_seen"] = current_time
            self.user_data[user_key]["user"] = user

            CHUNK_LIMIT = 5

            # データをバッファに溜める
            if self.user_data[user_key]["tick"] < CHUNK_LIMIT:
                self.user_data[user_key]["small_buffer"].append(data.pcm)
                self.user_data[user_key]["tick"] += 1

            else:
                # 溜まったbytesを結合してVAD判定
                self.user_data[user_key]["small_buffer"].append(data.pcm)
                big_buffer = b"".join(self.user_data[user_key]["small_buffer"])
                self.user_data[user_key]["small_buffer"].clear()
                self.user_data[user_key]["tick"] = 0

                tensor_data: torch.Tensor = self.vad.discord_to_silero(big_buffer)
                vad_result = self.vad.detect_voice(tensor_data)

                if vad_result:
                    if not self.user_data[user_key]["is_speaking"]:
                        asyncio.run_coroutine_threadsafe(
                            self.ws.send(create_state_message("listening")),
                            self.ev_loop
                        )
                    self.user_data[user_key]["is_speaking"] = True
                    
                    self.user_data[user_key]["buffer"].append(big_buffer)

                elif self.user_data[user_key]["is_speaking"]:
                    # 発話中の無音区間もバッファに追加
                    self.user_data[user_key]["buffer"].append(big_buffer)
        except Exception as e:
            print(f"write error: {e}")
            import traceback
            traceback.print_exc()

    async def process_conversation(self, user_key, raw_bytes):
        print("Processing...")
        try:
            send_bytes = struct.pack(">q", int(user_key)) + raw_bytes
            await self.ws.send(send_bytes)
            await self.ws.send(json.dumps({"type": "audio_end"}))

        except Exception as e:
            print(f"process_conversation error: {e}")
        
        finally:
            self.is_processing = False

    def cleanup(self):
        print("切断されました")

async def receiver_task(ws, play_queue: asyncio.Queue, sink: MyAudioSink):
    while True:
        try:
            data = await ws.recv()
            if isinstance(data, bytes):
                await play_queue.put(data)
            
            else:
                message = parse_client_message(data)
                if message["type"] == "state":
                    sink.ai_state = message["payload"]["state"]
                    print(f"receive message: {message['payload']['state']}")
                    continue
                
                elif message["type"] == "done":
                    sink.ai_state = "idle"
                    print("receiver_task done")
                    continue

                elif message["type"] == "error":
                    print(f"receive error: {message['payload']['message']}")
                    continue
        except Exception as e:
            print(f"receiver_task error: {e}")
            break



async def player_task(audio_queue, vc, loop):
    done_event = asyncio.Event()

    def after_callback(_error):
        loop.call_soon_threadsafe(done_event.set)

    while True:
        done_event.clear()
        try:
            audio_data = await audio_queue.get()
            if audio_data is None:
                break
            audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_data), pipe=True)
            vc.play(audio_source, after=after_callback)
            await done_event.wait()
            # print("再生終了")
        except Exception as e:
            print(f"player_taskで例外が発生しました: {e}")
            break

# FastAPI起動用関数
async def start_fastapi():
    config = uvicorn.Config(fastapi.app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def text_ws_receiver(ws):
    """receive all text_ws message and split it"""
    while True:
        data = await ws.recv()
        message = parse_client_message(data)

        if message["type"] == "text_response":
            text_response_queue.put_nowait(message["payload"]["text"])
        elif message["type"] == "state":
            print(f"text_ws_receiver AIState: {message['payload']['state']}")
        elif message["type"] == "emotion":
            print(f"text_ws_receiver emotion: {message['payload']['emotion']}")
        elif message["type"] == "error":
            print(f"text_ws_receiver error: {message['payload']['message']}")
        else:
            print(f"receive unknown message: message type is {message['type']}")

# ========== Bot Events ==========
@bot.event
async def on_ready():
    global text_ws
    text_ws = await websockets.connect("ws://localhost:8000/ws")
    asyncio.create_task(text_ws_receiver(text_ws))
    print('Logged in as Mashiro')

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    
    if message.attachments:
        image_url = message.attachments[0].url
    else:
        image_url = None

    # print(f"User: {message.content}")
    # print(f"user_id: {message.author.id}")

    async with message.channel.typing():
        await text_ws.send(create_text_message(
            message.author.id,
            message.content,
            image_url
        ))
        reply = await text_response_queue.get()
        print("websocketにメッセージを送信")

    if reply:
        reply = remove_thoughts(reply)

    try:
        if not reply:
            print("Empty reply generated. Skipping.")
            return 
    except Exception as e:
        print(f"on_message error: {e}")
    
    await message.reply(reply)

# ========== Bot Commands ==========
@bot.command()
async def join(ctx):
    global reconnect_enabled
    reconnect_enabled = True
    play_queue = asyncio.Queue()
    uri = "ws://localhost:8000/ws"
    ws = await websockets.connect(uri)
    channel = ctx.author.voice.channel
    loop = asyncio.get_event_loop()

    async def connect_and_listen():
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
        sink = MyAudioSink(vc, ws)
        vc.listen(sink)
        print("vc.listen 完了")
        bot.loop.create_task(receiver_task(ws, play_queue, sink)) # BG
        bot.loop.create_task(player_task(play_queue, vc, loop)) #BG
        return vc

    vc = await connect_and_listen()

    async def reconnect_loop():
        nonlocal vc
        while reconnect_enabled:
            try:
                await asyncio.sleep(1)
                if not vc.is_connected() and reconnect_enabled:
                    print("切断を検知。再接続を試みます...")
                    try:
                        try:
                            await vc.disconnect(force=True)
                        except:
                            pass
                        await asyncio.sleep(2)
                        vc = await connect_and_listen()
                        print("再接続完了！")
                    except Exception as e:
                        print(f"再接続失敗: {e}")
                        await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("再接続ループを終了します")
                break
            except Exception as e:
                print(f"再接続ループでエラー: {e}")
                if not reconnect_enabled:
                    break

    bot.loop.create_task(reconnect_loop())

@bot.command()
async def leave(ctx):
    global reconnect_enabled
    reconnect_enabled = False

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        print("正常に切断しました")

@bot.command()
async def callme(ctx, name: str):
    """呼び名を変更するコマンド"""
    profile.set_name(user_id=ctx.author.id, display_name=name)
    await ctx.reply(f"名前を{name}で記憶しました。")

"""
@bot.command()
async def clear(ctx):
    llm.clear_memory()
    await ctx.reply("記憶をリセットしました")
"""

# メインループ
async def main():
    async with bot:
        bot.loop.create_task(start_fastapi())
        await bot.start(f"{token}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
