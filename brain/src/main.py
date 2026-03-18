import discord
from memory.memory_store import UserProfileStore
from discord.ext import commands
from discord.ext import voice_recv
from dotenv import load_dotenv
import os
import asyncio
import time
import io
import logging
import uvicorn
import server.websocket as fastapi
import websockets
from server.protocol import parse_client_message, create_text_message
import re
from audiosink import MyAudioSink, VolumeMonitor
import utils.tools.discord_tool as discord_tool


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
# voice接続デバッグ用: discord内部ログをDEBUGに
logging.getLogger("discord.voice_client").setLevel(logging.DEBUG)
logging.getLogger("discord.voice_state").setLevel(logging.DEBUG)
logging.getLogger("discord.gateway").setLevel(logging.DEBUG)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.DEBUG)
os.environ["AV_LOG_LEVEL"] = "quiet"

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
profile = UserProfileStore()
text_response_queue = asyncio.Queue()
last_channel_id = None
last_voice_channel_id = None
vc = None
voice_ws = None
voice_tasks: list[asyncio.Task] = []
current_sink: MyAudioSink | None = None


def remove_thoughts(text: str) -> str:
    pattern = r"<think>.*?</think>"
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
    return cleaned_text.strip()



async def receiver_task(ws, play_queue: asyncio.Queue, sink: MyAudioSink):
    while True:
        try:
            data = await ws.recv()
            if isinstance(data, bytes):
                await play_queue.put(data)
            
            else:
                message = parse_client_message(data)
                if message["type"] == "state":
                    if message["payload"]["state"] == "speaking":
                        sink.interrupt_sent = False
                        sink.speaking_start_time = time.time()
                    sink.ai_state = message["payload"]["state"]
                    print(f"receive message: {message['payload']['state']}")
                    continue
                
                elif message["type"] == "done":
                    await play_queue.put("done")
                    print("receiver_task done")
                    continue

                elif message["type"] == "error":
                    print(f"receive error: {message['payload']['message']}")
                    continue
        except Exception as e:
            print(f"receiver_task error: {type(e).__name__}: {e}")
            break



async def player_task(audio_queue, vc, loop, sink: MyAudioSink):
    done_event = asyncio.Event()

    def after_callback(_error):
        loop.call_soon_threadsafe(done_event.set)

    while True:
        done_event.clear()
        try:
            audio_data = await audio_queue.get()
            if audio_data == "done":
                sink.ai_state = "idle"
                continue

            if audio_data is None:
                break
            
            audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_data), pipe=True, before_options="-loglevel error")
            audio_source_custom = VolumeMonitor(audio_source, fastapi.godot_queue, loop)
            sink.current_source = audio_source_custom
            if fastapi.godot_queue:
                await fastapi.godot_queue.put({"type": "state", "state": "speaking"})
            vc.play(audio_source_custom, after=after_callback)
            await done_event.wait()
            if fastapi.godot_queue:
                await fastapi.godot_queue.put({"type": "state", "state": "idle"})
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
            # print(f"text_ws_receiver AIState: {message['payload']['state']}")
            continue
        elif message["type"] == "emotion":
            print(f"text_ws_receiver emotion: {message['payload']['emotion']}")
        elif message["type"] == "error":
            print(f"text_ws_receiver error: {message['payload']['message']}")
        elif message["type"] == "finish":
            text_response_queue.put_nowait(None)
            print("text_ws_receiver finish received")
        else:
            print(f"receive unknown message: message type is {message['type']}")

async def discord_command_consumer():
    """discord_command_queueのコンシューマ"""
    global vc, voice_ws, voice_tasks, current_sink
    while True:
        if not fastapi.discord_command_queue:
            await asyncio.sleep(1.0)
            continue
        command = await fastapi.discord_command_queue.get()
        if command["type"] == "send_message":
            if last_channel_id is not None:
                channel = bot.get_channel(last_channel_id)
                if channel is not None:
                    await channel.send(command["text"])  # type: ignore[union-attr]
        elif command["type"] == "join_voice":
            await _cleanup_voice()
            if last_voice_channel_id is not None:
                loop = asyncio.get_event_loop()
                uri = "ws://localhost:8000/ws/voice"
                voice_ws = await websockets.connect(uri, ping_interval=None)
                channel = bot.get_channel(last_voice_channel_id)
                if channel is not None:
                    vc = await channel.connect(cls=voice_recv.VoiceRecvClient)  # type: ignore[union-attr]
                    if not vc.is_connected():
                        print(f"[ERROR] VC接続失敗 (autonomous): state={vc._connection.state}")
                        await _cleanup_voice()
                        continue
                    print(f"VC接続成功 (autonomous): state={vc._connection.state}")
                    sink = MyAudioSink(vc, voice_ws, loop)
                    current_sink = sink
                    vc.listen(sink)
                    print("vc.listen 完了")
                    voice_tasks.append(bot.loop.create_task(receiver_task(voice_ws, sink.play_queue, sink)))
                    voice_tasks.append(bot.loop.create_task(player_task(sink.play_queue, vc, loop, sink)))

        elif command["type"] == "leave_voice":
            await _cleanup_voice()


# ========== Bot Events ==========
@bot.event
async def on_ready():
    global text_ws
    text_ws = await websockets.connect("ws://localhost:8000/ws/text")
    asyncio.create_task(text_ws_receiver(text_ws))
    fastapi.discord_command_queue = asyncio.Queue()
    discord_tool.init(asyncio.get_event_loop(), fastapi.discord_command_queue)
    asyncio.create_task(discord_command_consumer())
    print('Logged in as Mashiro')

@bot.event
async def on_voice_state_update(member, before, after):
    global last_voice_channel_id
    if member.bot:
        return
    if after.channel is not None:
        last_voice_channel_id = after.channel.id
        

@bot.event
async def on_message(message: discord.Message):
    global last_channel_id
    if message.author.bot:
        return

    last_channel_id = message.channel.id

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    
    if message.attachments:
        image_url = message.attachments[0].url
    else:
        image_url = None

    async with message.channel.typing():
        await text_ws.send(create_text_message(
            message.author.id,
            message.content,
            image_url
        ))
        while True:
            reply = await text_response_queue.get()
            if reply is None:
                break
            print("websocketにメッセージを送信")

            if reply:
                reply = remove_thoughts(reply)

            try:
                if not reply:
                    print("Empty reply generated. Skipping.")
                    continue
            except Exception as e:
                print(f"on_message error: {e}")
                
            await message.reply(reply)

# ========== Bot Commands ==========
async def _cleanup_voice() -> None:
    """古い音声接続を全てクリーンアップする"""
    global vc, voice_ws, voice_tasks, current_sink

    # タスクをキャンセル
    for task in voice_tasks:
        task.cancel()
    voice_tasks.clear()

    # sink のバックグラウンドタスクをキャンセル
    if current_sink is not None:
        current_sink.bg_task.cancel()
        current_sink.queue_task.cancel()
        current_sink = None

    # WebSocket を閉じる
    if voice_ws is not None:
        try:
            await voice_ws.close()
        except Exception:
            pass
        voice_ws = None

    # Discord VC を切断 (接続失敗時もforce=Trueで確実にクリーンアップ)
    if vc is not None:
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass
    vc = None

@bot.command()
async def join(ctx):
    global vc, voice_ws, voice_tasks, current_sink

    await _cleanup_voice()

    uri = "ws://localhost:8000/ws/voice"
    voice_ws = await websockets.connect(uri, ping_interval=None)
    channel = ctx.author.voice.channel
    loop = asyncio.get_event_loop()

    vc = await channel.connect(cls=voice_recv.VoiceRecvClient)

    if not vc.is_connected():
        print(f"[ERROR] VC接続失敗: state={vc._connection.state}")
        await _cleanup_voice()
        await ctx.reply("ボイスチャンネルへの接続に失敗しました。もう一度試してください。")
        return

    print(f"VC接続成功: state={vc._connection.state}")
    sink = MyAudioSink(vc, voice_ws, loop)
    current_sink = sink
    vc.listen(sink)
    print("vc.listen 完了")
    voice_tasks.append(bot.loop.create_task(receiver_task(voice_ws, sink.play_queue, sink)))
    voice_tasks.append(bot.loop.create_task(player_task(sink.play_queue, vc, loop, sink)))

@bot.command()
async def leave(_ctx):
    await _cleanup_voice()
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
