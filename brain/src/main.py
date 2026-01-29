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
from myaudiosink import MyAudioSink
from memory.memory_store import MemoryStore, UserProfile

logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv").setLevel(logging.WARNING)

load_dotenv()

token = os.getenv("DISCORD_BOT_TOKEN")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
voice_client = None
reconnect_enabled = True  # 再接続フラグ

stt = STTEngine(device="cuda")
# backend: "llama" | "groq" | "gemini"
llm = LLMEngine(backend="llama")
tts = TTSEngine()

def remove_thoughts(text: str) -> str:
    pattern = r"\（思考:.*?\）"
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL)
    return cleaned_text.strip()

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
    print(f"User ID: {message.id}")
    loop = asyncio.get_running_loop()

    async with message.channel.typing():
        reply = await loop.run_in_executor(None, llm.generate, message.content)

    print(f"Reply: {reply}")
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


bot.run(f"{token}")
