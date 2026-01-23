import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm_engine import LLMEngine

llm = LLMEngine(2048)

response = llm.generate("こんにちはあなたの名前はなんですか？いまの時刻はわかりますか？やりたいことはありますか？")

print(response)

llm.clear_memory
print("clear memory")