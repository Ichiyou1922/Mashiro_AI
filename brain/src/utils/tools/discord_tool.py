import asyncio
_loop = None
_command_queue = None

def init(loop, queue):
    """main.pyのon_readyから呼ぶ。ループとキューを注入する"""
    global _loop, _command_queue
    _loop = loop
    _command_queue = queue

def _put_command(command: dict) -> str:
    """共通のコマンド送信ロジック"""
    if _loop is None or _command_queue is None:
        return "Discord未接続"
    future = asyncio.run_coroutine_threadsafe(_command_queue.put(command), _loop)
    future.result(timeout=3) # 完了待ち
    return "コマンドを送信しました"

def send_discord_message(text: str) -> str:
    _put_command({"type": "send_message", "text": text})
    return f"「{text}」をdiscordに送信しました。"

def join_voice() -> str:   
    _put_command({"type": "join_voice"})
    return "discordのVCに参加しました。"

def leave_voice() -> str:
    _put_command({"type": "leave_voice"})
    return "discordのVCから退出しました。"