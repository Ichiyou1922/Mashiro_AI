from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import torch
from brain.src.utils.audio_stream import ConversationSession


# グローバル変数
ml_models = {}

# 以下のlifespanハンドラでVADを常にロードしておく
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    print("Loading VAD model...")
    # Silero VADのロード
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=True
    )
    ml_models["vad_models"] = model
    ml_models["vad_utils"] = utils
    print("VAD model loaded.")

    yield # アプリ起動 ここがアプリ開始と終了の分かれ目

    # 終了の処理
    ml_models.clear()
    print("Clean up models.")

app = FastAPI(lifespan=lifespan)

@app.websocket("/ws/call")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    session = ConversationSession(
        websocket=websocket,
        vad_model=ml_models["vad_models"],
        vad_utils=ml_models["vad_utils"]
    )
    await session.start_call()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)