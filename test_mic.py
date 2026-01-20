import sys
import os
from brain.src.utils.audio_stream import MicrophoneStream
import numpy as np

# 音量メーターを表示するテスト
with MicrophoneStream(rate=16000, chunk=4096) as stream:
    print("マイクテスト開始 (Ctrl+Cで終了)...")
    for data in stream.generator():
        # バイナリデータを数値配列(float32)に変換
        audio_array = np.frombuffer(data, dtype=np.float32)
        
        # 音量（二乗平均平方根: RMS）を計算
        volume = np.sqrt(np.mean(audio_array**2))
        
        # 簡易的なバー表示
        bar = "#" * int(volume * 100) 
        print(f"\rVolume: {bar:<50}", end="")