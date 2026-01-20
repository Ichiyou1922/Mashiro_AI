import asyncio
import time

async def non_block_task(name, delay):
    print(f"Task {name}: start")
    # 制御権をイベントループに譲る（yield）
    # 「私は待ちに入りますので、他の人を動かしてください」という合図
    await asyncio.sleep(delay)
    print(f"Task {name}: done")

async def main_non_blocking():
    print("--- Non-Blocking Mode ---")
    start = time.perf_counter()
    
    # Task Aが待機に入った瞬間、Task Bが開始される
    await asyncio.gather(
        non_block_task("A", 2),
        non_block_task("B", 2)
    )
    
    # 合計時間は max(2, 2) = 2秒チョイで終わる
    print(f"Total time: {time.perf_counter() - start:.2f} sec")

if __name__ == "__main__":
    asyncio.run(main_non_blocking())