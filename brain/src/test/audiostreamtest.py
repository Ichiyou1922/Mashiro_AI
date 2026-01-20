import numpy as np
import torch
from silero_vad import load_silero_vad, get_speech_timestamps
import pyaudio
import wave

# Silero VAD モデルのロード
print("Loading Silero VAD model...")
model = load_silero_vad()

# マイク入力の設定
CHUNK = 16000  # フレームサイズ (1秒分のデータ)
FORMAT = pyaudio.paInt16  # 音声フォーマット
CHANNELS = 1  # モノラル
RATE = 16000  # サンプリングレート

# PyAudio ストリームを初期化
audio = pyaudio.PyAudio()
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)

# 音声の一時保存用
audio_buffer = []  # 音声データを一時的に保存する
is_recording = False  # 現在有音かどうかを管理
counter = 1

print("Listening for audio...")

try:
    while True:
        # マイクからデータを読み取り
        data = stream.read(CHUNK, exception_on_overflow=False)

        # バイナリデータをnumpy配列に変換
        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

        # Silero VADで音声活動を判定
        speech_timestamps = get_speech_timestamps(audio_data, model, sampling_rate=RATE)

        if speech_timestamps:
            # 音声が検出された場合
            print("発話開始")
            audio_buffer.append(data)  # 音声データをバッファに保存
            is_recording = True
        elif is_recording:
            # 「有音 → 無音」になった場合にファイルに保存
            print("発話終了")
            is_recording = False

            # バッファを結合
            full_audio = b"".join(audio_buffer)
            audio_buffer = []  # バッファをクリア

            # バッファをファイルに保存
            output_file = f"output_{counter}.wav"
            with wave.open(output_file, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(full_audio)

            print(f"ファイルに保存しました: {output_file}")
            counter += 1
        else:
            # 無音時
            print("...")
except KeyboardInterrupt:
    print("\n終了します...")
finally:
    # ストリームとリソースを解放
    stream.stop_stream()
    stream.close()
    audio.terminate()