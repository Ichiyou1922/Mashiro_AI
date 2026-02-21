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

config_name = "mashiro_config_v4.json"
model_name = "mashiro_v10.gguf"
MASHIRO_ID = int(os.getenv("MASHIRO_ID", "0"))

class LLMEngine:
    """
    LLMエンジン
    backend: "llama"
    """
    def __init__(self, n_ctx: int = 2048):
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

        print(f"LLM 準備完了")

    def _call_llm(self, messages: List[dict], response_format=None) -> str:
        """LLMを呼び出す共通関数"""
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
            response_format=response_format,
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
        print(f"[Debug LLM raw] '{answer_text}'")
        return answer_text

    def _clean_response(self, text: str) -> str:
        """LLMの応答から特殊トークンを除去する共通関数"""
        if '<function=' not in text:
            for s in ["<|im_end|>", "<|endoftext|>", "<think>", "</think>", "<end_of_turn>", "<start_of_turn>"]:
                text = text.replace(s, "")
            for s in ["ましろ:", "ましろ：", "[ツール実行結果]"]:
                text = text.removeprefix(s)
            pattern = r"^\[.*?]\s"
            text = re.sub(pattern, "", text)
            return text.strip()
        else:
            return text.strip()

    def generate(self, user_id: int, user_text: str, user_name: str="User", 
             save_user: bool=True, tool_context=None) -> dict:

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
                    memory_lines.append({"role": "user", "content": f"[ツール実行結果]: {sm['text']}"})
        
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
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "assistant", "content": tool_context["mashiro_function_calling"]}] + [{"role": "user", "content": f"[ツール実行結果]: {tool_context['tool_result']}\n\nuserに結果を教えてあげてください。"}]
            # print(messages)
        else:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "user", "content": f"{self.user_profile_store.get_name(user_id)}の発言" + user_text}]
        
        answer_text = self._call_llm(messages=messages, response_format={"type": "json_object"})
        
        try:
            result = json.loads(answer_text)
            result["text"] = self._clean_response(result.get("text", ""))
        except json.JSONDecodeError:
            print(f"JSONデコードエラー: {answer_text}")
            result = {}

        if save_user:
            memory_store.add_memory(
                text=user_text,
                user_id=user_id,
                user_name=display_name,
                role="user_message"
            )

        # print(f"[Debug] ましろ生: {answer_text}")
        # 特殊トークンの除去
        if result and result.get("text"):
            self.last_assistant_timestamp = memory_store.add_memory(
                text=result["text"],
                user_id=MASHIRO_ID,
                user_name="ましろ",
                role="assistant_message"
            )
        return result
    
    def generate_autonomous(self, impulse_text: str, tool_context: None) -> dict:
        """自己発話を生成する"""
        internal_signal = f"""
[内部シグナル] 
以下はあなたの潜在意識/身体からの衝動であり、ユーザーからの直接のメッセージではありません。
条件: {impulse_text} 
指示: この衝動に自然に反応してください。新しいトピックを始めたり、独り言を言ったり、検索したり、ユーザーに質問したりしても構いません。
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
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "assistant", "content": tool_context["mashiro_function_calling"]}] + [{"role": "ipython", "content": tool_context["tool_result"]}]
            # print(messages)
        else:
            messages = system_messages + scored_memory_lines + memory_lines + [{"role": "user", "content": internal_signal}]
            # print(messages)

        answer_text = self._call_llm(messages=messages, response_format={"type": "json_object"})

        try:
            result = json.loads(answer_text)
            result["text"] = self._clean_response(result.get("text", ""))
        except json.JSONDecodeError:
            print(f"JSONデコードエラー: {answer_text}")
            result = {}
        # print(f"[Debug] ましろ生: {answer_text}")
        # 特殊トークンの除去
        if result and result.get("text") and not result["text"].startswith("..."):
                self.last_assistant_timestamp = memory_store.add_memory(
                    text=result["text"],
                    user_id=MASHIRO_ID,
                    user_name="ましろ",
                    role="assistant_message"
                )
        return result
    
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
        # print(game_memory)
        answer_text = self._call_llm(messages=messages, response_format={"type": "json_object"})
        print(f"[Debug] ましろの戦略: {answer_text}")
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
        # constraints_text = "\n".join(config["constraints"])
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

## Tools
{tool_text}

## JSON Format
- text: ユーザーへの返答を書いてください。
- emotion: 返答の感情を以下の中から選んでください。neutral|happy|sad|angry|surprised|shy|sleepy|bored|question|wink
- speaking_rate: 話すスピードを指定してください。1.0が通常、0.8（ゆっくり）から1.5（速い）の範囲でfloatで指定してください。
- function: ツール呼び出しがある場合は、ツール名とパラメータをJSON形式で書いてください。ツールを使わない場合は "function": null です。
以下の例を参考にしてください。キーはいかなる場合においても必ずすべて出力してください。
例（ツール呼び出しなし）:
{{
    "text": "response here",
    "emotion": "neutral",
    "speaking_rate": 1.0,
    "function": null
}}
例（ツール呼び出しあり）:
{{
    "text": "ちょっと調べてみるね",
    "emotion": "neutral",
    "speaking_rate": 1.0,
    "function": {{"tool_name": "search_tool", "param": "検索したい内容"}}
}}
"""
        return prompt.strip()

