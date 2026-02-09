import sys
import os
# パス解決のおまじない
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llama_cpp import Llama
from dotenv import load_dotenv
from typing import cast, List, Any
import json
from memory.memory_store import MemoryStore, UserProfileStore, memory_store
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = ROOT_DIR / "models" / "llm"
CONFIG_PATH = ROOT_DIR / "config"


load_dotenv()

config_name = "mashiro_config_v2.json"
model_name = "mashiro_ai_v5.gguf"

class LLMEngine:
    """
    LLMエンジン
    backend: "llama"
    """
    def __init__(self, backend: str = "llama", n_ctx: int = 4096):
        self.backend = backend

        # 記憶関連
        self.user_profile_store = UserProfileStore()
        self.last_assistant_timestamp = None
        self.NEGATIVE_KEYWORDS = ["やめて", "違う", "そうじゃない", "嫌い", "違う"]
        self.counter = 0

        # 設定ファイル読み込み
        with open(f"{CONFIG_PATH}/{config_name}", "r", encoding="utf-8") as f: # システムプロンプト変えたらここも
            config = json.load(f)
        print("config loaded")
        self.system_prompt = self._build_prompt_without_examples(config)
        self.system_message = [{"role": "system", "content": self.system_prompt}]
        # 会話履歴の初期化
        for ex in config["examples"]:
            self.system_message.append({"role": "user", "content": ex["user"]})
            self.system_message.append({"role": "assistant", "content": ex["assistant"]})

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

        else:
            raise ValueError(f"Unknown backend: {backend}")

        print(f"LLM 準備完了 (backend: {backend})")

    def generate(self, user_id: int, user_text: str, user_name: str = "User") -> str:
        print("Thinking...")
        saved_name = self.user_profile_store.get_name(user_id=user_id)
        display_name = saved_name if saved_name else user_name

        if any(kw in user_text for kw in self.NEGATIVE_KEYWORDS):
            delta = -0.2
            if self.last_assistant_timestamp is not None:
                memory_store.adjust_importance(self.last_assistant_timestamp, delta=delta)
            else:
                print("[generate] timestampの取得に失敗しました。")

        memories = memory_store.search_with_score(user_text)

        if memories:
            sorted_memories = sorted(memories, key=lambda m: m["timestamp"])
            memory_lines = []
            for m in sorted_memories:
                if m["role"] == "user_message":
                    memory_lines.append(f"{m['user_name']}: {m['text']}")
                elif m["role"] == "assistant_message":
                    memory_lines.append(f"ましろ: {m['text']}")
            memory_content = "\n".join(memory_lines)
        else:
            memory_content = "なし"
        
        # ユーザー発言 + コンテキスト
        full_message = f"""[記憶]
{memory_content}

[現在の発言]
{display_name}: {user_text}
"""
        messages = self.system_message + [{"role": "user", "content": full_message}]
        # ========== Llama ==========
        if self.backend == "llama":
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
            memory_store.add_memory(
                text=user_text,
                user_id=user_id,
                user_name=display_name,
                role="user_message"
            )
            # adjust_importanceのためにtimestampを保持
            self.last_assistant_timestamp = memory_store.add_memory(
                text=answer_text,
                user_id=user_id,
                user_name=display_name,
                role="assistant_message"
            )
            self.counter += 1
            if self.counter >= 20:
                memory_store.evaluate_importance()
                self.counter = 0

        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        # 特殊トークンの除去
        for s in ["<|im_end|>", "<|endoftext|>", "<think>", "</think>", "<end_of_turn>", "<start_of_turn>"]:
            answer_text = answer_text.replace(s, "")
        answer_text = answer_text.strip()
        return answer_text
    
    def generate_stream(self, user_id: int, user_text: str, user_name: str = 'User'):
        """ストリーミング生成（Llama専用）"""
        if self.backend != "llama":
            raise NotImplementedError(f"generate_stream is not supported for {self.backend}")
        
        STOP_TOKENS = {'<|im_end|>', '<|endoftext|>', '<end_of_turn>', '<start_of_turn>', '</s>', '[INST]', '[/INST]', '<s>'}

        print("Thinking...")

        saved_name = self.user_profile_store.get_name(user_id=user_id)
        display_name = saved_name if saved_name else user_name

        if any(kw in user_text for kw in self.NEGATIVE_KEYWORDS):
            delta = -0.2
            if self.last_assistant_timestamp is not None:
                memory_store.adjust_importance(self.last_assistant_timestamp, delta=delta)
            else:
                print("[generate] timestampの取得に失敗しました。")

        memories = memory_store.search_with_score(user_text)

        if memories:
            sorted_memories = sorted(memories, key=lambda m: m["timestamp"])
            memory_lines = []
            for m in sorted_memories:
                if m["role"] == "user_message":
                    memory_lines.append(f"{m['user_name']}: {m['text']}")
                elif m["role"] == "assistant_message":
                    memory_lines.append(f"ましろ: {m['text']}")
            memory_content = "\n".join(memory_lines)
        else:
            memory_content = "なし"
        
        # ユーザー発言 + コンテキスト
        full_message = f"""[記憶]
{memory_content}

[現在の発言]
{display_name}: {user_text}
"""
        messages = self.system_message + [{"role": "user", "content": full_message}]

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
            memory_store.add_memory(
                text=user_text,
                user_id=user_id,
                user_name=display_name,
                role="user_message"
            )
            self.last_assistant_timestamp = memory_store.add_memory(
                text=full_response,
                user_id=user_id,
                user_name=display_name,
                role="assistant_message"
            )
            self.counter += 1
            if self.counter >= 20:
                memory_store.evaluate_importance()
                self.counter = 0

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
