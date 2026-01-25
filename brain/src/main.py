import discord
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from discord.ext import commands
from discord.ext import voice_recv
from dotenv import load_dotenv
import os
import asyncio
import numpy as np
import torch
import time
import io
import re

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
voice_client = None
reconnect_enabled = True  # 再接続フラグ

stt = STTEngine()
llm = LLMEngine(2048)
tts = TTSEngine()

def remove_thoughts(text: str) -> str:
    # pattern: （思考: 任意の文字）
    # re.DOTALL: 改行を含めてマッチさせる
    pattern = r"\（思考:.*?\）"
    # マッチした部分を空文字で置換
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
    return cleaned_text.strip()

class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, stt_engine: STTEngine, llm_engine: LLMEngine, tts_engine: TTSEngine, vc):
        super().__init__()
        self.stt = stt_engine
        self.llm = llm_engine
        self.tts = tts_engine
        self.ev_loop = bot.loop

        # ユーザーごとの音声バッファ（話者ごとに処理したい）
        self.user_data = {}

        # ユーザーごとの最後にwriteが呼ばれた時刻を記録するためのタスク
        self.bg_task = self.ev_loop.create_task(self.check_silence_loop())

        # 音声再生用
        self.vc = vc

        self.is_processing = False
    
    def wants_opus(self) -> bool:
        return False

    async def check_silence_loop(self):
        print("Watchdog started.")
        while True:
            await asyncio.sleep(0.1)

            if self.is_processing:
                continue
            
            current_time = time.time()
            for user_key in list(self.user_data.keys()):

                # 喋り中？
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

                        # Processを起動
                        self.ev_loop.create_task(
                            self.process_conversation(user_key, full_audio_bytes)
                        )
    
    # 誰かがしゃべるたびにこのメソッドが20msごとに呼ばれ続ける
    def write(self, user, data: bytes) -> bytes | None:
        # ユーザーが特定できないパケットは無視
        if user is None or user.bot:
            return
        
        # data.pcmは bytes型のPCMデータ
        try:
            pcm_data = data.pcm
        except AttributeError:
            # 本当にOpusが来てしまっているのか
            print(f"Error: Data has no .pcm attribute. Type: {type(data)}")
            return
        # ユーザーごとのバッファを生成
        user_key = str(user.id)
        current_time = time.time()

        # 初期化
        if user_key not in self.user_data:
            self.user_data[user_key] = {
                "buffer": [],
                "small_buffer": [],
                "tick": 0,
                "is_speaking": False,
                "last_seen": current_time
                }

        # パケット受信のたびにlast_seenを更新
        self.user_data[user_key]["last_seen"] = current_time

        CHUNK_LIMIT = 5

        # 2. データをバッファに溜める
        if self.user_data[user_key]["tick"] < CHUNK_LIMIT: # 0.1秒間データを溜めてからdiscord_to_sileroに投げる
            self.user_data[user_key]["small_buffer"].append(data.pcm)
            self.user_data[user_key]["tick"] += 1
            
        else:
            # 溜まったbytesを結合してdiscord_to_sileroに渡す
            self.user_data[user_key]["small_buffer"].append(data.pcm)
            big_buffer = b"".join(self.user_data[user_key]["small_buffer"])
            self.user_data[user_key]["small_buffer"].clear()
            self.user_data[user_key]["tick"] = 0
            # VAD判定
            tensor_data: torch.Tensor = self.stt.discord_to_silero(big_buffer)
            
            # byte_termから話しているか話していないか判別して分岐
            # 話しているならまた溜める
            # 話していないならLLM->TTSの流れに入る
            if self.stt.detect_voice(tensor_data):
                self.user_data[user_key]["is_speaking"] = True
                self.user_data[user_key]["buffer"].append(big_buffer)

            elif self.user_data[user_key]["is_speaking"]:
                self.user_data[user_key]["buffer"].append(big_buffer)

    async def process_conversation(self, user_key, raw_bytes):
        print("Processing...")

        loop = asyncio.get_running_loop()
        try:
            audio_input = await loop.run_in_executor(None, self.stt.convert_for_whisper, raw_bytes)
            text = await loop.run_in_executor(None, self.stt.transcribe, audio_input)

            if text:
                print(f"User: {text}")
                response = await loop.run_in_executor(None, self.llm.generate, text)

                if response is None:
                    print("Error: No response")
                    return

                print(response)
                clean_response = remove_thoughts(response)

                audio_bytes = await self.tts.synthesize(clean_response)
                if audio_bytes is None:
                    print("Error: TTS returned None")
                    return

                audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_bytes), pipe=True)
                await play_and_wait(self.vc, audio_source)  

        finally:
            self.is_processing = False
    def cleanup(self):
        # 切断時の処理
        print("切断されました")

async def play_and_wait(vc, source):
    loop = asyncio.get_running_loop()
    done_event = asyncio.Event()

    def after_callback(error):
        loop.call_soon_threadsafe(done_event.set)

    vc.play(source, after=after_callback)
    await done_event.wait()
    print("Debug: 再生終了通知を受け取りました")



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
    print(message.content)
    reply = llm.generate(message.content)
    print(reply)
    await message.reply(remove_thoughts(reply))

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

    # 自動再接続ループ
    async def reconnect_loop():
        nonlocal vc
        while reconnect_enabled:
            try:
                await asyncio.sleep(1)
                # 切断されていたら再接続
                if not vc.is_connected() and reconnect_enabled:
                    print("切断を検知。再接続を試みます...")
                    try:
                        # 既存の接続をクリーンアップ
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
    reconnect_enabled = False  # 再接続を無効化

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        print("正常に切断しました")


        



bot.run(f"{token}")
