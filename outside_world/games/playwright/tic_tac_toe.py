import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../"))
from base import GameBase
from playwright.async_api import async_playwright
import asyncio

class TicTacToe(GameBase):
    URL = "https://collect777.com/tic-tac-toe/"

    def get_rules(self) -> str:
        rule = """
- まるばつゲームです。
- 3×3の盤面に対戦者と交代でマルとバツを置きます。
- 先行がバツを使い、後攻がマルを使います。
- 盤面は1行目左から1, 2, 3, 2行目左から4, 5, 6, 3行目左から7, 8, 9とします。
- 先に縦、横、斜めいずれかにマークを揃えたプレイヤーが勝利です。
"""
        return rule
    
    async def game_loop(self):
        if not self.page:
            print("game-loop error")
            return

        await self.page.goto(self.URL)
        await self.page.click("#playerVsPlayer")
        # await self.page.wait_for_selector(".space")
        await self.page.wait_for_selector("#board", state="visible")

        while True:
            # === ましろのターン ===
            await self.page.wait_for_timeout(500)
            field_context = await self.get_context()
            availables = await self.get_available_actions()
            await self.send_context(field_context, f"置ける位置: {', '.join(availables)}")
            action = await self.receive_action()
            if action:
                await self.execute_action(action)
            # ましろが勝ったか確認
            board_menu = await self.page.query_selector("#boardMenu")
            if board_menu and await board_menu.is_visible():
                break
            # === ユーザーのターン ===
            available_before = set(await self.get_available_actions())
            while True:
                await self.page.wait_for_timeout(200)
                available_now = set(await self.get_available_actions())
                if available_now != available_before:
                    break
            # ユーザーが勝ったか確認
            board_menu = await self.page.query_selector("#boardMenu")
            if board_menu and await board_menu.is_visible():
                break

            # 状態の送信
            field_context_after_action = await self.get_context()
            await self.send_action_result(field_context_after_action)
            continue

    async def get_context(self) -> str:
        if self.page:
            # .spaceクラスを持つ要素を全部取得 -> 9ツのセル
            cells = await self.page.query_selector_all(".space")

            board = {}
            for cell in cells:
                # class属性の値を取得 -> "space c2 r2"
                class_attr = await cell.get_attribute("class")
                # テキスト内容を取得 -> "X" / "O" / ""
                text = await cell.text_content()

                # "space c2 r2" を分割 -> ["space", "c2", "r2"]
                if class_attr:
                    classes = class_attr.split()
                
                # "c2" -> 2 のように数字を取り出す
                col = int( [c for c in classes if c.startswith("c")][0][1:] )
                row = int( [c for c in classes if c.startswith("r")][0][1:] )

                # 行・列から1 ~ 9 に変換
                cell_num = (row - 1) * 3 + col
                board[cell_num] = text.strip() if text.strip() else "_"
            return f"""
{board[1]}|{board[2]}|{board[3]} (1|2|3)
----------
{board[4]}|{board[5]}|{board[6]} (4|5|6)
----------
{board[7]}|{board[8]}|{board[9]} (7|8|9)
"""
    
    async def get_available_actions(self):
        cells = await self.page.query_selector_all(".space")
        board = {}
        for cell in cells:
            class_attr = await cell.get_attribute("class")
            text = await cell.text_content()
            if class_attr:
                classes = class_attr.split()
            col = int( [c for c in classes if c.startswith("c")][0][1:] )
            row = int( [c for c in classes if c.startswith("r")][0][1:] )

            # 行・列から1 ~ 9 に変換
            cell_num = (row - 1) * 3 + col
            board[cell_num] = text.strip() if text.strip() else "_"
        available = [str(k) for k in board if board[k] == "_"]
        return available

    async def execute_action(self, action: str):
        cell_num = int(action)
        row = (cell_num -1) // 3 + 1
        col = (cell_num -1) % 3 + 1
        await self.page.click(f".c{col}.r{row}")


if __name__ == "__main__":
    tictactoe = TicTacToe("tictactoe")
    try:
        asyncio.run(tictactoe.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()