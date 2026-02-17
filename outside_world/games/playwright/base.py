from playwright.async_api import async_playwright, Playwright
import asyncio
import websockets
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))
from brain.src.server.protocol import create_action_result_message, create_game_start_message, create_context_request_message, parse_client_message
class GameBase:
    def __init__(self, game_name: str):
        self.game_name = game_name
        self.ws_uri = "ws://localhost:8000/ws/game"
        self.page = None
        self.ws = None
        self.playwright = None
        self.browser = None

    async def connect(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        self.ws = await websockets.connect(self.ws_uri)

    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.playwright:
            await self.playwright.stop()

    async def run(self):
        await self.connect()
        if self.ws:
            await self.ws.send(create_game_start_message(self.game_name, self.get_rules()))
        else:
            print("ws connect error")
        await self.game_loop()
        await self.close()

    async def send_context(self, context: str, action_request: str):
        if self.ws:
            await self.ws.send(create_context_request_message(context, action_request))
        else:
            print("send_context failed")
        
    async def send_action_result(self, result: str):
        if self.ws:
            await self.ws.send(create_action_result_message(result))
        else:
            print("send_action_result failed")

    async def receive_action(self):
        if self.ws:
            while True:
                data = await self.ws.recv()
                message = parse_client_message(str(data))
                if message["type"] == "action":
                    return message["payload"]["action"]
        else:
            print("receive_action error")

    # === サブクラスが実装するメソッド ===
    async def game_loop(self):
        raise NotImplementedError
    
    def get_rules(self) -> str:
        raise NotImplementedError
    
    async def get_context(self) -> str:
        raise NotImplementedError
    
    async def execute_action(self, action: str):
        raise NotImplementedError