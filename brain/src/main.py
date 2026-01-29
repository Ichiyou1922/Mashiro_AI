import discord
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from discord.ext import commands
from discord.ext import voice_recv
from dotenv import load_dotenv
import os
import asyncio
import torch
import time
import io
import re
import logging

logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.WARNING)

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
reconnect_enabled = True  # 再接続フラグ

stt = STTEngine(device="cuda")
# backend: "llama" | "groq" | "gemini"
llm = LLMEngine(backend="llama")
tts = TTSEngine()
"""
def remove_thoughts(text: str) -> str:
    pattern = r"\（思考:.*?\）"
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
    return cleaned_text.strip()
"""
def remove_thoughts(text: str) -> str:
    text = text.replace("<think>", "").replace("</think>", "")
    return text.strip()

# ========== AudioSink ==========
class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, stt_engine: STTEngine, llm_engine: LLMEngine, tts_engine: TTSEngine, vc):
        super().__init__()
        self.stt = stt_engine
        self.llm = llm_engine
        self.tts = tts_engine
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

    def wants_opus(self) -> bool:
        return False

    async def process_queue_loop(self):
        """キューから音声データを取り出して順番に処理するワーカー"""
        while True:
            user, user_key, audio_bytes = await self.audio_queue.get()
            await self.process_conversation(user, user_key, audio_bytes)

    async def check_silence_loop(self):
        print("Watchdog started.")
        while True:
            await asyncio.sleep(0.1)

            # Processing中はスキップ
            if self.is_processing:
                continue

            current_time = time.time()
            for user_key in list(self.user_data.keys()):

                # 喋り中でなければスキップ
                if not self.user_data[user_key]["is_speaking"]:
                    continue

                # 最後のパケットから0.5秒以上経過してる？
                silence_duration = current_time - self.user_data[user_key]["last_seen"]

                if silence_duration > 1.0:
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

            tensor_data: torch.Tensor = self.stt.discord_to_silero(big_buffer)
            vad_result = self.stt.detect_voice(tensor_data)

            if vad_result:
                self.user_data[user_key]["is_speaking"] = True
                self.user_data[user_key]["buffer"].append(big_buffer)

            elif self.user_data[user_key]["is_speaking"]:
                # 発話中の無音区間もバッファに追加
                self.user_data[user_key]["buffer"].append(big_buffer)

    async def process_conversation(self, user, user_key, raw_bytes):
        print("Processing...")

        loop = asyncio.get_running_loop()
        try:
            audio_input = await loop.run_in_executor(None, self.stt.convert_for_whisper, raw_bytes)
            text = await loop.run_in_executor(None, self.stt.transcribe, audio_input)

            if text:
                print(f"User: {text}")
                print("Thinking...")
                response = await loop.run_in_executor(
                    None, self.llm.generate, int(user_key), text, user.display_name
                )

                if response is None:
                    print("Error: No response")
                    return

                print(response)
                clean_response = remove_thoughts(response)

                print("Synthesizing...")
                audio_bytes = await self.tts.synthesize(clean_response)
                if audio_bytes is None:
                    print("Error: TTS returned None")
                    return

                audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_bytes), pipe=True)
                await play_and_wait(self.vc, audio_source)

        finally:
            self.is_processing = False

    def cleanup(self):
        print("切断されました")

async def play_and_wait(vc, source):
    loop = asyncio.get_running_loop()
    done_event = asyncio.Event()

    def after_callback(_error):
        loop.call_soon_threadsafe(done_event.set)

    vc.play(source, after=after_callback)
    await done_event.wait()
    print("再生終了")

# ========== Bot Events ==========
@bot.event
async def on_ready():
    print('Logged in as Mashiro')

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    print(f"User: {message.content}")
    print(f"User ID: {message.author.id}")
    loop = asyncio.get_running_loop()

    async with message.channel.typing():
        reply = await loop.run_in_executor(
            None, llm.generate, message.author.id, message.content, message.author.display_name
        )

    print(f"Reply: {reply}")
    clean_reply = remove_thoughts(reply)
    if not clean_reply:
        print("Empty reply generated. Skipping.")
        return 
    
    await message.reply(clean_reply)

# ========== Bot Commands ==========
@bot.command()
async def join(ctx):
    global reconnect_enabled
    reconnect_enabled = True

    channel = ctx.author.voice.channel
    async def connect_and_listen():
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
        sink = MyAudioSink(stt, llm, tts, vc)
        vc.listen(sink)
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
    llm.user_profile_store.set_name(user_id=ctx.author.id, display_name=name)
    await ctx.reply(f"名前を{name}で記憶しました。")

@bot.command()
async def clear(ctx):
    llm.clear_memory()
    await ctx.reply("記憶をリセットしました")


bot.run(f"{token}")
