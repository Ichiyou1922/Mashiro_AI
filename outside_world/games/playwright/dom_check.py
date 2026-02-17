import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://collect777.com/tic-tac-toe/")

        # --- 選択画面のDOM ---
        print("=" * 60)
        print("【選択画面】")
        html = await page.content()
        print(html)

        # --- 1人モードを選択 ---
        await page.click("#playerVsCPU")
        await page.wait_for_selector(".space")

        print("=" * 60)
        print("【ゲーム開始直後】")
        html = await page.content()
        print(html)

        # --- 1手打つ（1番のセルをクリック） ---
        await page.click(".c1.r1")
        await page.wait_for_timeout(2000)  # CPUが打つまで待つ

        print("=" * 60)
        print("【1手後（CPU応答後）】")
        html = await page.content()
        print(html)

        # 手動で残りを確認する時間
        await asyncio.sleep(60)

asyncio.run(inspect())
