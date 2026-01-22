import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.stt_engine import STTEngine
import numpy as np
import torch

stt = STTEngine()

test_bytes = np.zeros(48000 * 2, dtype=np.int16)

for i in range(len(test_bytes)):
    test_bytes[i] = np.random.randint(-32768, 32768)

result = stt.discord_to_silero(test_bytes.tobytes())

print(result.shape)
print(isinstance(result, torch.Tensor))
print(result.max() < 1)
print(result.min() > -1)