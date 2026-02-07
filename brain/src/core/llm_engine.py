import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen25VLChatHandler
from dotenv import load_dotenv
from typing import cast, List, Any
import json
from groq import Groq
from google import genai
from google.genai import types
from memory.memory_store import MemoryStore, UserProfileStore
import re
from pathlib import Path
from collections import deque

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = ROOT_DIR / "models" / "llm"
CONFIG_PATH = ROOT_DIR / "config"


load_dotenv()

GROQ_KEY = os.getenv("GROQ_API")
GOOGLE_KEY = os.getenv("GOOGLE_API")
config_name = "mashiro_config_v2.json"
model_name = "mashiro_ai_v5.gguf"

class LLMEngine:
    """
    LLMエンジン
    backend: "llama" | "groq" | "gemini"
    """
    def __init__(self, backend: str = "llama", n_ctx: int = 4096):
        self.backend = backend

        # 記憶関連
        self.memory_store = MemoryStore()
        self.user_profile_store = UserProfileStore()

        # 設定ファイル読み込み
        with open(f"{CONFIG_PATH}/{config_name}", "r", encoding="utf-8") as f: # システムプロンプト変えたらここも
            config = json.load(f)
        print("config loaded")
        self.system_prompt = self._build_prompt_without_examples(config)
        self.system_message = [{"role": "system", "content": self.system_prompt}]
        # 会話履歴の初期化（Llama/Groq用）
        for ex in config["examples"]:
            self.system_message.append({"role": "user", "content": ex["user"]})
            self.system_message.append({"role": "assistant", "content": ex["assistant"]})
        
        self.conversation_history = deque(maxlen=10)

        # ========== Llama (ローカル) ==========
        if backend == "llama":
            self.llm_path = os.path.expanduser(
                f"{MODEL_PATH}/{model_name}"
            )
            self.llm_model = Llama(
                model_path=self.llm_path,
                n_gpu_layers=-1, # -1だと全レイヤーをGPUに
                n_ctx=n_ctx,
                # cache_type_k="q8_0",
                # cache_type_v="q8_0",
                chat_format = "chatml",
                # chat_format="gemma",
                verbose=False
            )

        # ========== Groq ==========
        elif backend == "groq":
            self.groq_client = Groq(
                api_key=os.environ.get("GROQ_API_KEY", f"{GROQ_KEY}")
            )
            self.groq_model = "llama-3.1-8b-instant"

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

        past_memories = self.memory_store.search_memory(user_text)

        # 記憶を整形
        if past_memories:
            memories_list = []
            for m in past_memories:
                formatted_memory = m['text'].replace(chr(10), ' / ')
                memories_list.append(formatted_memory)

            memories_text = "\n".join(memories_list)
        else:
            memories_text = "なし"

        context_prompt = f"""
[基本情報]
- ユーザーの名前: {display_name}
- あなたの名前: ましろ

[記憶]
{memories_text}
        """
        print(context_prompt)
        full_context = f"[コンテキスト]\n{context_prompt}\n\n[{display_name}の発言]\n{user_text}"
        # ========== Llama ==========
        if self.backend == "llama":
            self.conversation_history.append({"role": "user", "content": full_context})
            messages = self.system_message + list(self.conversation_history)
            response = cast(dict[str, Any], self.llm_model.create_chat_completion(
                messages=cast(List[Any], messages),
                max_tokens=1024,
                temperature=1.0,
                top_k=64,
                top_p=0.95,
                # repeat_penalty=1.15,
                # frequency_penalty=0.3,
                # presence_penalty=0.2,
                stream=False,
                stop=[
                    # Gemma
                    "<end_of_turn>",
                    "<start_of_turn>",
                    # ChatML (Qwen等)
                    "<|im_end|>",
                    "<|endoftext|>",
                    # Llama
                    "</s>",
                    "[INST]",
                    "[/INST]",
                    "<s>",
                    # 共通
                    "\nUser:",
                    "[コンテキスト]",
                    "[/CONTEXT]",
                    ]
            ))
            answer_text: str = response['choices'][0]['message']['content'] or ""
            self.memory_store.add_memory(
                text=f"{display_name}: {user_text} / ましろ: {answer_text}",
                user_id=user_id,
                user_name=display_name,
                role="interaction"
            )
        
        

        # ========== Groq ==========
        elif self.backend == "groq":
            self.conversation_history.append({"role": "user", "content": full_context})
            messages = self.system_message + list(self.conversation_history)
            chat_completion = self.groq_client.chat.completions.create(
                messages=cast(List[Any], messages),
                model=self.groq_model,
                temperature=0.9,
                max_completion_tokens=256,
                top_p=1,
                stop=None,
                stream=False,
            )
            answer_text: str = chat_completion.choices[0].message.content or ""

        # ========== Gemini ==========
        elif self.backend == "gemini":
            response = self.gemini_chat.send_message(user_text)
            answer_text = response.text or ""

        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        # 特殊トークンの除去
        for s in ["<|im_end|>", "<|endoftext|>", "<think>", "</think>", "<end_of_turn>", "<start_of_turn>"]:
            answer_text = answer_text.replace(s, "")
        answer_text = answer_text.strip()

        # アシスタントの応答を履歴に追加
        if self.backend in ["llama", "groq"]:
            self.conversation_history.append({"role": "assistant", "content": answer_text})

        return answer_text
    
    def generate_stream(self, user_id: int, user_text: str, user_name: str = 'User'):
        """ストリーミング生成（Llama専用）"""
        if self.backend != "llama":
            raise NotImplementedError(f"generate_stream is not supported for {self.backend}")

        print("Thinking...")

        saved_name = self.user_profile_store.get_name(user_id=user_id)
        display_name = saved_name if saved_name else user_name

        past_memories = self.memory_store.search_memory(user_text)

        STOP_TOKENS = {'<|im_end|>', '<|endoftext|>', '<end_of_turn>', '<start_of_turn>', '</s>', '[INST]', '[/INST]', '<s>'}

        # 記憶を整形
        if past_memories:
            memories_list = []
            for m in past_memories:
                formatted_memory = m['text'].replace(chr(10), ' / ')
                memories_list.append(formatted_memory)

            memories_text = "\n".join(memories_list)
        else:
            memories_text = "なし"

        context_prompt = f"""
[基本情報]
- ユーザーの名前: {display_name}
- あなたの名前: ましろ

[記憶]
{memories_text}
        """
        full_context = f"[コンテキスト]\n{context_prompt}\n\n[{display_name}の発言]\n{user_text}"
        self.conversation_history.append({"role": "user", "content": full_context})
        messages = self.system_message + list(self.conversation_history)

        response = self.llm_model.create_chat_completion(
            messages=cast(List[Any], messages),
            max_tokens=1024,
            temperature=1.0,
            top_k=64,
            top_p=0.95,
            stream=True,
            stop=[
                # Gemma
                "<end_of_turn>",
                "<start_of_turn>",
                # ChatML (Qwen等)
                "<|im_end|>",
                "<|endoftext|>",
                # Llama
                "</s>",
                "[INST]",
                "[/INST]",
                "<s>",
                # 共通
                "\nUser:",
                "[コンテキスト]",
                "[/CONTEXT]",
                ]
        )

        full_response = ""
        try:
            for chunk in response:
                chunk = cast(dict[str, Any], chunk)
                delta = chunk['choices'][0]['delta']
                if 'content' in delta:
                    content: str = delta['content'] or ""
                    if content not in STOP_TOKENS:
                        full_response += content
                        yield content

        finally:
            # アシスタントの応答を履歴に追加
            if full_response:
                print(full_response)
                self.conversation_history.append({"role": "assistant", "content": full_response})
            
            self.memory_store.add_memory(
                    text=f"{display_name}: {user_text} / ましろ: {full_response}",
                    user_id=user_id,
                    user_name=display_name,
                    role="interaction"
                )

    def clear_memory(self):
        print("Clearing History")
        self.conversation_history.clear()

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
        identity_text = "\n".join(config["identity"])
        personality_text = "\n".join(config["personality"])
        autonomy_text = "\n".join(config["autonomy"])
        speech_style_text = "\n".join(config["speech_style"])
        constraints_text = "\n".join(config["constraints"])
        tool_text = "\n".join(config["tools"])

        prompt = f"""
Name: {config['name']}

## Identity
{identity_text}

## Personality
{personality_text}

## Autonomy
{autonomy_text}

## Speech Style
{speech_style_text}

## Constraints
{constraints_text}

## Tools
{tool_text}
"""
        return prompt.strip()
