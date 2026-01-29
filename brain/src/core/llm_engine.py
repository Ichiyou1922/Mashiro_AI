import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llama_cpp import Llama
from dotenv import load_dotenv
import os
from typing import cast, List, Any
import json
from groq import Groq
from google import genai
from google.genai import types
from memory.memory_store import MemoryStore, UserProfileStore


load_dotenv()

GROQ_KEY = os.getenv("GROQ_API")
GOOGLE_KEY = os.getenv("GOOGLE_API")

class LLMEngine:
    """
    LLMエンジン
    backend: "llama" | "groq" | "gemini"
    """
    def __init__(self, backend: str = "gemini", n_ctx: int = 4096):
        self.backend = backend

        # 記憶関連
        self.memory_store = MemoryStore()
        self.user_profile_store = UserProfileStore()

        # 設定ファイル読み込み
        with open("/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/config/mashiro_config.json", "r", encoding="utf-8") as f: # システムプロンプト変えたらここも
            config = json.load(f)

        self.system_prompt = self._build_prompt_without_examples(config)

        # 会話履歴の初期化（Llama/Groq用）
        self.history = [{"role": "system", "content": self.system_prompt}]
        for ex in config["examples"]:
            self.history.append({"role": "user", "content": ex["user"]})
            self.history.append({"role": "assistant", "content": ex["assistant"]})

        # ========== Llama (ローカル) ==========
        if backend == "llama":
            self.llm_path = os.path.expanduser(
                "/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/models/llm/qwen3-4b-abliterated-q4_k_m.gguf"
            )
            self.llm_model = Llama(
                model_path=self.llm_path,
                n_gpu_layers=-1,
                n_ctx=n_ctx,
                # cache_type_k="q8_0",
                # cache_type_v="q8_0",
                # chat_format="gemma",
                verbose=False
            )

        # ========== Groq ==========
        elif backend == "groq":
            self.groq_client = Groq(
                api_key=os.environ.get("GROQ_API_KEY", f"{GROQ_KEY}")
            )
            self.groq_model = "llama-3.3-70b-versatile"

        # ========== Gemini ==========
        elif backend == "gemini":
            self.gemini_client = genai.Client(api_key=GOOGLE_KEY)
            self.gemini_model = "gemini-2.5-flash"
            self.gemini_chat = self.gemini_client.chats.create(
                model=self.gemini_model,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    max_output_tokens=256,
                )
            )

        else:
            raise ValueError(f"Unknown backend: {backend}")

        print(f"LLM 準備完了 (backend: {backend})")

    def generate(self, user_id: int, user_text: str, user_name: str = "User") -> str:
        print("Thinking...")
        saved_name = self.user_profile_store.get_name(user_id=user_id)
        display_name = saved_name if saved_name else user_name

        past_memories = self.memory_store.search_memory(user_text, user_id=user_id)

        # 記憶を整形
        if past_memories:
            memories_text = "\n".join([f"- {m.replace(chr(10), ' / ')}" for m in past_memories])
        else:
            memories_text = "なし"

        context_prompt = f"今話している人の名前: {display_name}\n過去の会話:\n{memories_text}"
        full_context = f"[コンテキスト]\n{context_prompt}\n\n[{display_name}の発言]\n{user_text}"
        # ========== Llama ==========
        if self.backend == "llama":
            self.history.append({"role": "user", "content": full_context})
            response = self.llm_model.create_chat_completion(
                messages=cast(List[Any], self.history),
                max_tokens=300,
                temperature=1.0,
                top_k=64,
                top_p=0.95,
                stream=False,
                stop=[
                    "<end_of_turn>"
                    "<|im_end|>", 
                    # "<|endoftext|>", 
                    # "User:",
                    "\nUser:",
                    "</s>",
                    "[INST]",
                    # "[/INST]",
                    "<s>"
                    ]
            )
            answer_text = response['choices'][0]['message']['content'] or ""
            self.memory_store.add_memory(
                text=f"User: {user_text}\nAssistant: {answer_text}",
                user_id=user_id,
                user_name=user_name,
                role="interaction"
            )

        # ========== Groq ==========
        elif self.backend == "groq":
            self.history.append({"role": "user", "content": user_text})
            chat_completion = self.groq_client.chat.completions.create(
                messages=self.history,
                model=self.groq_model,
                temperature=0.7,
                max_completion_tokens=256,
                top_p=1,
                stop=None,
                stream=False,
            )
            answer_text = chat_completion.choices[0].message.content or ""

        # ========== Gemini ==========
        elif self.backend == "gemini":
            response = self.gemini_chat.send_message(user_text)
            answer_text = response.text or ""

        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        # 特殊トークンの除去
        for s in ["<|im_end|>", "<|endoftext|>"]:
            answer_text = answer_text.replace(s, "")
        answer_text = answer_text.strip()

        # 簡易的なヒストリー解放（Llama/Groq用）
        if self.backend in ["llama", "groq"]:
            while len(self.history) > 20:
                print("Forgetting old memories...")
                self.history.pop(1)
            if answer_text:
                self.history.append({"role": "assistant", "content": answer_text})

        return answer_text

    def generate_stream(self, user_text: str):
        """ストリーミング生成（Llama専用）"""
        if self.backend != "llama":
            raise NotImplementedError(f"generate_stream is not supported for {self.backend}")

        print("Thinking...")
        self.history.append({"role": "user", "content": user_text})

        response = self.llm_model.create_chat_completion(
            messages=cast(List[Any], self.history),
            max_tokens=256,
            temperature=0.7,
            repeat_penalty=1.1,
            frequency_penalty=0.1,
            presence_penalty=0.1,
            stream=True
        )

        full_response = ""
        for chunk in response:
            delta = chunk['choices'][0]['delta']
            if 'content' in delta:
                content = delta['content']
                full_response += content
                yield content
        self.history.append({"role": "assistant", "content": full_response})

    def clear_memory(self):
        print("Clearing History")
        self.history = [self.history[0]]  # system promptだけ残す

        # Geminiの場合はchatも再作成
        if self.backend == "gemini":
            self.gemini_chat = self.gemini_client.chats.create(
                model=self.gemini_model,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    max_output_tokens=256,
                )
            )

    def _build_prompt_without_examples(self, config):
        guidelines_text = "\n".join(config["guidelines"])
        speech_style_text = "\n".join(config["speech_style"])

        prompt = f"""
Name: {config['name']}

## Guidelines
{guidelines_text}

## Speech Style
{speech_style_text}

/no_think
"""
        return prompt.strip()
