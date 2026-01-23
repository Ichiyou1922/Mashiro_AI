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

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")

llm = LLMEngine(4096)

bot = commands.Bot(command_prefix="", intents=discord.Intents.all())

class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, stt_engine: STTEngine, llm_engine: LLMEngine, tts_engine: TTSEngine):
        super().__init__()
        self.stt = stt_engine
        self.llm = llm_engine
        self.tts = tts_engine

        # ユーザーごとの音声バッファ（話者ごとに処理したい）
        self.buffers = {}

        # 秒数のカウントのため
        self.tickcount = 0

        # 無音判定のためのカウントと、状態
        self.count = 0
        self.is_speaking = False
    
    # 誰かがしゃべるたびにこのメソッドが20msごとに呼ばれ続ける
    def write(self, user, data: bytes) -> bytes | None:
        # ユーザーごとのバッファを生成
        userkey, textkey = f'{user}', b'textbyte'
        self.buffers[userkey] = user
        if user not in self.buffers:
            self.buffers[textkey] = []
        # data.pcmは bytes型のPCMデータ
        # 1. userがBot自信なら無視
        if user.bot:
            return
        
        # 2. データをバッファに溜める
        if self.tickcount < 25: # 0.5秒間データを溜めてからdiscord_to_sileroに投げる
            self.buffers[textkey].append(data)
            self.tickcount += 1
            
        else:
            # 溜まったbytesを結合してdiscord_to_sileroに渡す
            byte_term = b"".join(self.buffers[textkey])
            tensor_data: torch.Tensor = self.stt.discord_to_silero(byte_term)

            # byte_termから話しているか話していないか判別して分岐
            # 話しているならまた溜める
            # 話していないならLLM->TTSの流れに入る
            if self.stt.detect_voice(tensor_data):
                self.is_speaking = True
                self.tickcount = 0
                return

            elif self.is_speaking:
                self.count += 1
                if self.count > 1:
                    full_audio = b"".join(self.buffers[textkey])
                    ndarray_audio = np.frombuffer(full_audio, dtype=np.float32)
                    text_to_llm: str = self.stt.transcribe(ndarray_audio)
                    # LLMに送る
                    response = self.llm.generate(text_to_llm)
                    # TTSに送る
                    response_audio = self.tts.synthesize(response)
                    # バッファのクリア
                    self.buffers.clear()
                    self.count = 0
                    self.llm.clear_memory()
                    

    def cleanup(self):
        # 切断時の処理


@bot.event
async def on_ready():
    print(f'Logged in as MashiroAI!')
'''
@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')
'''


bot.run(f"{token}")
