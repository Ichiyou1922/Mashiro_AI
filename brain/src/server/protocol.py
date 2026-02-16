import json
from typing import Literal, Optional


# 型定義

# クライアント -> サーバーのメッセージタイプ
ClientMessageType = Literal[
    "audio_end", 
    "interrupt", 
    "cancel", 
    "text_message", 
    "autonomous"
    ]

# サーバー -> クライアントのメッセージタイプ
ServerMessageType = Literal[
    "state", 
    "subtitle", 
    "llm_token", 
    "done", 
    "error", 
    "text_response", 
    "emotion", 
    "volume"
    ]

# AI状態
AIState = Literal[
    "idle", 
    "listening", 
    "thinking", 
    "speaking", 
    "sleeping"
    ]

# ゲーム用
ClientGameMessageType = Literal[
    "game_start",
    "context",
    "action_request",
    "action_result"
]

ServerGameMessageType = "action"

def create_game_start_message(game_name: str):
    """ゲームの開始を知らせるメッセージの作成"""
    return json.dumps({
        "type": "game_start",
        "payload": {"game": game_name}
    })

def create_context_request_message(message: str, action_request: str = ''):
    """ゲームの状況を知らせ、行動可能な選択肢を包んだメッセージの作成"""
    return json.dumps({
        "type": "context",
        "payload": {"context": message, "action_request": action_request}
    })

def create_action_result_message(message: str):
    """action実行後の結果を知らせるメッセージの作成"""
    return json.dumps({
        "type": "action_result",
        "payload": {"action_result": message}
    })

def create_action_message(message: str):
    """LLMの行動を知らせるメッセージの作成"""
    return json.dumps({
        "type": "action",
        "payload": {"action": message}
    })



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

def create_volume_message(volume: float) -> str:
    """音声のvolumeメッセージを作成"""
    return json.dumps({
        "type": "volume",
        "payload": {"volume": volume}
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

def create_autonomous_message(text):
    """自己発話レスポンスを作成"""
    return json.dumps({
        "type": "autonomous",
        "payload": {
            "text": text
        }
    })