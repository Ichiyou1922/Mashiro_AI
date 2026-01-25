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
import uuid
import io

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="", intents=discord.Intents.all())
voice_client = None

stt = STTEngine()
llm = LLMEngine(4098)
tts = TTSEngine()

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

        # LLMのセグフォ対策
        # アクセスロック ＋ キュ＝（最新のテキストのみ処理）
        self.current_task_id = None
        self.llm_lock = asyncio.Lock()

        # 音声再生用
        self.vc = vc
    
    def wants_opus(self) -> bool:
        return False

    async def check_silence_loop(self):
        print("Watchdog started.")
        while True:
            await asyncio.sleep(0.1)
            
            current_time = time.time()
            for user_key in list(self.user_data.keys()):

                # 喋り中？
                if not self.user_data[user_key]["is_speaking"]:
                    continue

                # 最後のパケットから0.5秒以上経過してる？
                silence_duration = current_time - self.user_data[user_key]["last_seen"]

                if silence_duration > 0.5:
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
                print(".", end="", flush=True)
                self.user_data[user_key]["is_speaking"] = True
                self.user_data[user_key]["buffer"].append(big_buffer)
                
                

            elif self.user_data[user_key]["is_speaking"]:
                self.user_data[user_key]["buffer"].append(big_buffer)

    async def process_conversation(self, user_key, raw_bytes):
        task_id = uuid.uuid4()
        self.current_task_id = task_id

        print("Processing...")

        # STTでrun_in_executor を使う（STTは重い）
        loop = asyncio.get_running_loop()

        audio_input = await loop.run_in_executor(None, self.stt.convert_for_whisper, raw_bytes)

        text = await loop.run_in_executor(None, self.stt.transcribe, audio_input)
        
        async with self.llm_lock:
            # ロック取得時に自分が最新化チェックする
            if self.current_task_id != task_id:
                return 
            
            if text:
                print(f"User: {text}")
                # LLMは重い？重ければexecutorへ入れる。いれておくか
                response = await loop.run_in_executor(None, self.llm.generate, text)
                print(response)
                if type(response) == None:
                    print("Error: No response")
                    return

                # TTSはasyncなのでそのままawait
                audio_bytes = await self.tts.synthesize(response)
                if audio_bytes is None:
                    print("Error: TTS returned None")
                    return
                audio_source = discord.FFmpegPCMAudio(io.BytesIO(audio_bytes), pipe=True)

                # 再生処理
                if self.vc.is_playing():
                    print("audio is playing so after stop it and play")
                    self.vc.stop()
                    self.vc.play(audio_source)
                else:
                    print("audio is playing")
                    self.vc.play(audio_source)
                    

    def cleanup(self):
        # 切断時の処理
        print("切断されました")





@bot.event
async def on_ready():
    print('Logged in as Mashiro')

@bot.command()
async def join(ctx):
    channel = ctx.author.voice.channel

    vc = await channel.connect(cls=voice_recv.VoiceRecvClient)

    sink = MyAudioSink(stt, llm, tts, vc)
    
    vc.listen(sink)

    # await ctx.send("喋っていいよ")
        



bot.run(f"{token}")
