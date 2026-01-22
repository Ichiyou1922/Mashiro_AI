from llama_cpp import Llama
from dotenv import load_dotenv
import os
from typing import cast, List, Any

load_dotenv()

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")

class LLMEngine:
    def __init__(self, n_ctx):
        self.llm_path = os.path.expanduser("/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/models/llm/Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf")
        self.system_prompt = SYSTEM_PROMPT
        self.llm_model = Llama(
            model_path = self.llm_path,
            n_gpu_layers=-1,
            n_ctx=n_ctx,
            verbose=False
        )
        # 会話履歴の初期化
        self.history = [{"role": "system", "content": self.system_prompt}]
        
        print("LLM 準備完了")

    def generate_stream(self, user_text: str):
        print("Thinking...")
        self.history.append({"role": "user", "content": user_text})

        response = self.llm_model.create_chat_completion(
            messages=cast(List[Any], self.history),
            max_tokens=256,
            temperature=0.7,
            stream=True
        )

        # ストリーミングで表示
        
        full_response = ""
        for chunk in response:
            # チャンクからテキストを取り出す
            delta = chunk['choices'][0]['delta']
            if 'content' in delta:
                content = delta['content']
                full_response += content
                yield content
        self.history.append({"role": "assistant", "content": full_response})
        
    def generate(self, user_text: str):
        print("Thinking...")
        self.history.append({"role": "user", "content": user_text})

        response = self.llm_model.create_chat_completion(
            messages=cast(List[Any], self.history),
            max_tokens=256,
            temperature=0.7,
            stream=False
        )
        answer_text = response['choices'][0]['message']['content']
        self.history.append({"role": "assistant", "content": answer_text})
        return answer_text
        
    
    def clear_memory(self):
        print("Clearing History")
        self.history.clear()


