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
import re

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = ROOT_DIR / "models" / "llm"
CONFIG_PATH = ROOT_DIR / "config"


load_dotenv()

config_name = "mashiro_config_v3.json"
model_name = "mashiro_v10.gguf"
MASHIRO_ID = int(os.getenv("MASHIRO_ID"))

class LLMEngine:
    """
    LLMエンジン
    backend: "llama"
    """
    def __init__(self, backend: str = "llama", n_ctx: int = 2048):
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
        # self.system_message = [{"role": "system", "content": self.system_prompt}]

        '''
        # 会話履歴の初期化
        for ex in config["examples"]:
            self.system_message.append({"role": "user", "content": ex["user"]})
            self.system_message.append({"role": "assistant", "content": ex["assistant"]})
        '''
        # ========== Llama (ローカル) ==========
        if backend == "llama":
            self.llm_path = os.path.expanduser(
                f"{MODEL_PATH}/{model_name}"
            )
            self.llm_model = Llama(
                model_path=self.llm_path,
                n_gpu_layers=-1, # -1だと全レイヤーをGPUに
                n_ctx=n_ctx,
                # cache_type_k="q4_0",
                # cache_type_v="q4_0",
                # chat_format = "qwen",
                chat_format="llama-3",
                flash_attn=True,
                verbose=False
            )

        else:
            raise ValueError(f"Unknown backend: {backend}")

        print(f"LLM 準備完了 (backend: {backend})")

    def generate(self, user_id: int, user_text: str, user_name: str="User", 
             save_user: bool=True, tool_context=None) -> str:

        print("Thinking...")
        saved_name = self.user_profile_store.get_name(user_id=user_id)
        display_name = saved_name if saved_name else user_name

        if any(kw in user_text for kw in self.NEGATIVE_KEYWORDS):
            delta = -0.2
            if self.last_assistant_timestamp is not None:
                memory_store.adjust_importance(self.last_assistant_timestamp, delta=delta)
                print("importanceを減少させました。")
            else:
                print("[generate] timestampの取得に失敗しました。")

        # memories = memory_store.search_with_score(user_text, limit=3)

        """
        if memories:
            timestamps = [memory["timestamp"] for memory in memories]
            memory_store.mark_accessed(timestamps)
            sorted_memories = sorted(memories, key=lambda m: m["timestamp"])
            memory_lines = []
            for m in sorted_memories:
                if m["role"] == "user_message":
                    memory_lines.append(f"{m['user_name']}: {m['text']}")
                elif m["role"] == "assistant_message":
                    memory_lines.append(f"{m['user_name']}: {m['text']}")
            memory_content = "\n".join(memory_lines)
        else:
            memory_content = "なし"
        """
        reflections = memory_store.get_reflection(limit=3)
        if reflections:
            reflection_text = "\n".join([f"- {r['text']}" for r in reflections])
            print("===reflection===")
            print(reflection_text)
            system_content = self.system_prompt + f"\n\n## Memory\n{reflection_text}"
        else:
            system_content = self.system_prompt
        
        system_messages = [{"role": "system", "content": system_content}]

        memory_lines = []
        short_memory = memory_store.get_short_term()
        if short_memory:
            for sm in short_memory:
                if sm["role"] == "user_message":
                    memory_lines.append({"role": "user", "content": f"{sm['user_name']}: {sm['text']}"})
                elif sm["role"] == "assistant_message":
                    memory_lines.append({"role": "assistant", "content": f"{sm['text']}"})
                elif sm["role"] == "tool_result":
                    memory_lines.append({"role": "ipython", "content": f"{sm['text']}"})
        
        reversed_memory_lines = memory_lines[-3:]
        query_line = ''
        for item in reversed_memory_lines:
            query_line += str(item['content'])
        query_line += user_text
        scored_memory = memory_store.search_with_score(query=query_line, limit=2)
        scored_memory_lines = []
        if scored_memory:
            for sm in scored_memory:
                if sm["role"] == "user_message":
                    scored_memory_lines.append({"role": "user", "content": f"{sm['user_name']}: {sm['text']}"})
                elif sm["role"] == "assistant_message":
                    scored_memory_lines.append({"role": "assistant", "content": f"{sm['text']}"})
        print("===scored memory===")
        print(scored_memory_lines)
        print("===memory===")
        print(memory_lines)
        if tool_context is not None:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "assistant", "content": tool_context["mashiro_function_calling"]}] + [{"role": "ipython", "content": tool_context["tool_result"]}]
            # print(messages)
        else:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "user", "content": f"{self.user_profile_store.get_name(user_id)}の発言" + user_text}]
        
        # ========== Llama ==========
        if self.backend == "llama":
            response = cast(dict[str, Any], self.llm_model.create_chat_completion(
                messages=cast(List[Any], messages),
                max_tokens=1024,
                temperature=1.0,
                #top_k=64,
                #top_p=0.95,
                repeat_penalty=1.1,
                frequency_penalty=0.3,
                presence_penalty=0.2,
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
            if save_user == True:
                memory_store.add_memory(
                    text=user_text,
                    user_id=user_id,
                    user_name=display_name,
                    role="user_message"
                )
    
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        # print(f"[Debug] ましろ生: {answer_text}")
        # 特殊トークンの除去
        if '<function=' not in answer_text:
            for s in ["<|im_end|>", "<|endoftext|>", "<think>", "</think>", "<end_of_turn>", "<start_of_turn>"]:
                answer_text = answer_text.replace(s, "")
            for s in ["ましろ:", "ましろ：", "[ツール実行結果]"]:
                answer_text = answer_text.removeprefix(s)
            pattern = r"^\[.*?]\s"
            answer_text = re.sub(pattern, "", answer_text)
            answer_text = answer_text.strip()
            # adjust_importanceのためにtimestampを保持
            self.last_assistant_timestamp = memory_store.add_memory(
                text=answer_text,
                user_id=MASHIRO_ID,
                user_name="ましろ",
                role="assistant_message"
            )
        return answer_text
    
    def generate_autonomous(self, impulse_text: str, tool_context: None, user_name: str = 'User'):
        """自己発話を生成する"""
        internal_signal = f"""
[内部シグナル] 
以下はあなたの潜在意識/身体からの衝動であり、ユーザーからの直接のメッセージではありません。
条件: {impulse_text} 
指示: この衝動に自然に反応してください。新しいトピックを始めたり、独り言を言ったり、ユーザーに質問したりしても構いません。
"""
        reflections = memory_store.get_reflection(limit=3)
        if reflections:
            reflection_text = "\n".join([f"- {r['text']}" for r in reflections])
            print("===reflection===")
            print(reflection_text)
            system_content = self.system_prompt + f"\n\n## Memory\n{reflection_text}"
        else:
            system_content = self.system_prompt
        
        system_messages = [{"role": "system", "content": system_content}]

        memory_lines = []
        short_memory = memory_store.get_short_term()
        if short_memory:
            for sm in short_memory:
                if sm["role"] == "user_message":
                    memory_lines.append({"role": "user", "content": f"{sm['user_name']}: {sm['text']}"})
                elif sm["role"] == "assistant_message":
                    memory_lines.append({"role": "assistant", "content": f"{sm['text']}"})
                elif sm["role"] == "tool_result":
                    memory_lines.append({"role": "ipython", "content": f"{sm['text']}"})
        
        reversed_memory_lines = memory_lines[-3:]
        query_line = ''
        for item in reversed_memory_lines:
            query_line += str(item['content'])
        scored_memory = memory_store.search_with_score(query=query_line, limit=2)
        scored_memory_lines = []
        if scored_memory:
            for sm in scored_memory:
                if sm["role"] == "user_message":
                    scored_memory_lines.append({"role": "user", "content": f"{sm['user_name']}: {sm['text']}"})
                elif sm["role"] == "assistant_message":
                    scored_memory_lines.append({"role": "assistant", "content": f"{sm['text']}"})
                
        print("===scored memory===")
        print(scored_memory_lines)
        print("===memory===")
        print(memory_lines)
        if tool_context is not None:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "assistant", "content": tool_context["mashiro_function_calling"]}] + [{"role": "ipython", "content": tool_context["tool_result"]}] + [{"role": "user", "content": internal_signal}]
            # print(messages)
        else:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "user", "content": internal_signal}]
            # print(messages)

        response = cast(dict[str, Any], self.llm_model.create_chat_completion(
            messages=cast(List[Any], messages),
            max_tokens=1024,
            temperature=1.0,
            #top_k=64,
            #top_p=0.95,
            repeat_penalty=1.1,
            frequency_penalty=0.3,
            presence_penalty=0.2,
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

        # print(f"[Debug] ましろ生: {answer_text}")
        # 特殊トークンの除去
        if '<function=' not in answer_text:
            for s in ["<|im_end|>", "<|endoftext|>", "<think>", "</think>", "<end_of_turn>", "<start_of_turn>"]:
                answer_text = answer_text.replace(s, "")
            for s in ["ましろ:", "ましろ：", "[ツール実行結果]"]:
                answer_text = answer_text.removeprefix(s)
            pattern = r"^\[.*?]\s"
            answer_text = re.sub(pattern, "", answer_text)
            answer_text = answer_text.strip()
            # adjust_importanceのためにtimestampを保持
            if not answer_text.startswith("..."):
                self.last_assistant_timestamp = memory_store.add_memory(
                    text=answer_text,
                    user_id=MASHIRO_ID,
                    user_name="ましろ",
                    role="assistant_message"
                )
        return answer_text
    
    def generate_game_action(
            self, 
            context: str, 
            action_request: str, 
            game_memory: list, 
            game_rules: str,
            skill_library: list = []
            ) -> dict:
        print("Thinking strategy...")

        system_content = self.system_prompt + f"\n\n## Game Rule\n{game_rules}"
        system_message = [{"role": "system", "content": system_content}]

        user_content = f"""[Current State]
{context}
        
[Next Action List]
{action_request}

[Output Format]
以下のJSONキーで必ず回答してください:
- "action": Next Action Listから選んだアクション
- "text": そのアクションへのコメント（ましろとして）
例: {{"action": "選んだアクション", "text": "コメント"}}"""

        messages = system_message + game_memory + [{"role": "user", "content": user_content}]
        print(game_memory)
        response = cast(dict[str, Any], self.llm_model.create_chat_completion(
            messages=cast(List[Any], messages),
            max_tokens=1024,
            temperature=1.0,
            #top_k=64,
            #top_p=0.95,
            repeat_penalty=1.1,
            frequency_penalty=0.3,
            presence_penalty=0.2,
            stream=False,
            response_format={"type": "json_object"},
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

        answer_text = response['choices'][0]['message']['content'] or ''
        print(answer_text)
        try:
            return json.loads(answer_text)
        except json.JSONDecodeError as jd:
            print(f"generate_game_action json decode error: {jd}")
            return {}
    
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
