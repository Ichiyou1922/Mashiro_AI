import discord
from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from discord.ext import commands
from discord.ext import voice_recv
from dotenv import load_dotenv
import os
import asyncio
load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")

llm = LLMEngine(4096)

class CustomSink(voice_recv.AudioSink):
    def __init__(self):
        super().__init__()
    
    def writes(self, user, data):
        # 音声データ（PCM）が来る
        # user: 喋っている人間
        # data.pcm: 音声データ
        if not user.bot:
            print(f"Received audio from {user.name}: {len(data.pcm)} bytes")
            # stt_engineに流す

bot = commands.Bot(command_prefix="", intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f'Logged in as MashiroAI!')
'''
@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')
'''

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    else:
        llm.generate_stream(message)
bot.run(f"{token}")
