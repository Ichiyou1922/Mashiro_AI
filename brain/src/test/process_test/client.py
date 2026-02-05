import asyncio
import websockets

async def test_echo():
    # サーバーURL
    uri = "ws://localhost:8000/ws"

    async with websockets.connect(uri) as websocket:
        while True:
            # 入力を受け付ける
            msg = input("You: ")

            # サーバへ送信
            await websocket.send(msg)

            # サーバからの応答を待つ
            response = await websocket.recv()
            print(f"Server: {response}")

if __name__ == "__main__":
    asyncio.run(test_echo())
