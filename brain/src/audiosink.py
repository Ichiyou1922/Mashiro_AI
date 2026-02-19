import discord
import numpy as np
from discord.ext import voice_recv
import asyncio
import time
import torch
from server.protocol import create_state_message, create_interrupt_message
from core.vad_engine import VADEngine
import struct
import json

# ========== Custom AudioSource =========
class VolumeMonitor(discord.AudioSource):
    def __init__(self, original, godot_queue, loop):
        self.original = original
        self.godot_queue = godot_queue
        self.loop = loop
        self.muted = False

    def read(self) -> bytes:
        data = self.original.read()
        if not data:
            return data
        if self.muted:
            return b'\x00' * len(data)

        # RMS
        try:
            if self.godot_queue is not None:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                volume = np.sqrt(np.mean(np.square(samples)))
                asyncio.run_coroutine_threadsafe(
                    self.godot_queue.put({"type": "volume", "volume": float(volume)}),
                    self.loop
                )
        except Exception as e:
            print(f"VolumeMonitor error: {e}")
        
        return data
    
    def cleanup(self) -> None:
        try:
            return self.original.cleanup()
        except Exception:
            pass

# ========== AudioSink ==========
class MyAudioSink(voice_recv.AudioSink):
    def __init__(self, vc, ws, loop):
        print("MyAudioSink __init__ 開始")
        super().__init__()
        self.vad = VADEngine()
        self.ev_loop = loop
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
        # interrupt用のフラグ
        self.interrupt_sent = False
        
        self.play_queue = asyncio.Queue()
        self.should_cleanup = True
        self.speaking_start_time: float
        self.current_source: VolumeMonitor | None = None


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

    def _do_interrupt(self):
        """イベントループスレッドで実行される"""
        if self.current_source:
            self.current_source.muted = True
        while not self.play_queue.empty():
            self.play_queue.get_nowait()
    
    def wants_to_stop_without_cleanup(self):
        self.should_cleanup = False

    def write(self, user, data) -> None:
        try:
            # ユーザーが特定できないパケットは無視
            if user is None or user.bot:
                return

            # 実験的に実装: AIが話している間はユーザーの発話を無視
            if self.ai_state == "speaking" or self.is_processing:
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
                        self.user_data[user_key]["speech_start_time"] = current_time
                        asyncio.run_coroutine_threadsafe(
                            self.ws.send(create_state_message("listening")),
                            self.ev_loop
                        )
                    self.user_data[user_key]["is_speaking"] = True
                    self.user_data[user_key]["buffer"].append(big_buffer)

                    # 割り込み判定: VADが声を検知 かつ ましろが発話中
                    '''
                    if (self.ai_state == "speaking"
                        and not self.interrupt_sent):
                        self.interrupt_sent = True
                        print("interrupt detected!")
                        asyncio.run_coroutine_threadsafe(
                            self.ws.send(create_interrupt_message()),
                            loop=self.ev_loop
                        )
                        self.ev_loop.call_soon_threadsafe(self._do_interrupt)
                    '''
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
        if not self.should_cleanup:
            return
        else:
            print("切断されました")