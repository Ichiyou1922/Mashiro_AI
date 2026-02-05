import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.tts_engine import TTSEngine
import pyaudio
import wave

WAVE_OUTPUT_FILENAME="test.wav"
CHANNELS=1
FORMAT=pyaudio.paInt16
RATE=48000

tts = TTSEngine()
p = pyaudio.PyAudio()
result = tts.synthesize("こんにちは")
if result is None:
    print("Error: TTSエンジンが音声データを返しませんでした")
    exit(1)

print(f"Audio data size: {len(result)} bytes")

wavFile = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wavFile.setnchannels(CHANNELS)
wavFile.setsampwidth(2)
wavFile.setframerate(RATE)
wavFile.writeframes(result)
wavFile.close()

print(f"Finished Recording - Saved to {WAVE_OUTPUT_FILENAME}")

p.terminate()