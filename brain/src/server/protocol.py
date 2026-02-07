import json
from typing import Literal, Optional


# 型定義

# クライアント -> サーバーのメッセージタイプ
ClientMessageType = Literal["audio_end", "interrupt", "cancel", "text_message"]

# サーバー -> クライアントのメッセージタイプ
ServerMessageType = Literal["state", "subtitle", "llm_token", "done", "error", "text_response", "emotion"]

# AI状態
AIState = Literal["idle", "listening", "thinking", "speaking"]

# メッセージ作成関数
def create_state_message(state: AIState) -> str:
    """AI状態メッセージの作成"""
    return json.dumps({
        "type": "state",
        "payload": {"state": state}
    })

def create_subtitle_message(text: str, is_user: bool) -> str:
    """字幕メッセージの作成"""
    return json.dumps({
        "type": "subtitle",
        "payload": {"text": text, "is_user": is_user}
    })

def create_llm_token_message(token: str) -> str:
    """LLMトークンメッセージを作成"""
    return json.dumps({
        "type": "llm_token",
        "payload": {"token": token}
    })

def create_done_message() -> str:
    """完了メッセージの作成"""
    return json.dumps({"type": "done"})

def create_error_message(message: str) -> str:
    """エラーメッセージを作成"""
    return json.dumps({
        "type": "error",
        "payload": {"message": message}
    })

def create_emotion_message(emotion: str) -> str:
    return json.dumps({
        "type": "emotion",
        "payload": {"emotion": emotion}
    })

# メッセージ解析関数
def parse_client_message(data: str) -> dict:
    """クライアントからのJSONメッセージを解析"""
    return json.loads(data)

def create_text_message(user_id, text, image_url=None):
    """discordからのメッセージを作成"""
    if image_url:
        return json.dumps({
            "type": "text_message",
            "payload": {
                "user_id": user_id,
                "text": text,
                "image_url": image_url
            }
        })
    
    return json.dumps({
        "type": "text_message",
        "payload": {
            "user_id": user_id,
            "text": text
        }
    })

def create_text_response_message(text):
    """LLMのレスポンスを作成"""
    return json.dumps({
        "type": "text_response",
        "payload": {
            "text": text
        }
    })