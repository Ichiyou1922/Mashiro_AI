from typing import List
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.activate_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.activate_connections.append(websocket)
        print("WebSocket connection established.")
    
    def disconnect(self, websocket: WebSocket):
        self.activate_connections.remove(websocket)
        print("WebSocket connection closed.")
    
    async def send_audio(self, websocket: WebSocket, audio_data: bytes):
        await websocket.send_bytes(audio_data)