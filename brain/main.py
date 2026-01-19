from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

@app.websocket("/ws")
async def echo_endpoint(websocket: WebSocket):
    # 接続を受け入れる
    await websocket.accept()
    print("Connection established.")

    try:
        while True:
            # クライアントからのメッセージを待つ（受信）
            data = await websocket.receive_text()
            print(f"Received: {data}")

            # 受け取ったものを返す（送信）
            await websocket.send_text(data)

    except WebSocketDisconnect:
        print("Connection closed.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)