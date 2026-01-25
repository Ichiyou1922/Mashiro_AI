from llama_cpp import Llama
from dotenv import load_dotenv
import os
from typing import cast, List, Any
import json



class LLMEngine:
    def __init__(self, n_ctx):
        self.llm_path = os.path.expanduser("/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/models/llm/qwen2.5-3b-instruct-abliterated-q4_k_m.gguf")
        self.llm_model = Llama(
            model_path = self.llm_path,
            n_gpu_layers=-1,
            n_ctx=n_ctx,
            verbose=False
        )

        with open("/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/config/mashiro_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        self.system_prompt = self._build_prompt(config)
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
            repeat_penalty=1.1,
            presence_penalty=0.1,
            stream=False
        )
        answer_text = response['choices'][0]['message']['content']
        self.history.append({"role": "assistant", "content": answer_text})
        return answer_text
        
    
    def clear_memory(self):
        print("Clearing History")
        self.history.clear()

    def _build_prompt(self, config):
        # リストを結合 →読みやすいテキストに
        guidelines_text = "\n".join(config["guidelines"])
        speech_style_text = "\n".join(config["speech_style"])

        # 会話例(Few-Shot)
        examples_text = ""
        for ex in config["examples"]:
            examples_text += f"User: {ex['user']}\nMashiro: {ex['assistant']}\n"

        # make prompt
        prompt = f"""
Name: {config['name']}

## Guidelines
{guidelines_text}

## Speech Style
{speech_style_text}

## Dialogue Examples
{examples_text}
"""
        return prompt.strip()

