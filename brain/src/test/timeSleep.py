import asyncio
import time

async def block_task(name, delay):
    print(f"Task {name}: start")
    # ここでイベントループごとスレッドが停止する
    # 他のタスクは実行のチャンスすら与えられない
    time.sleep(delay)
    print(f"Task {name}: done")

async def main_blocking():
    print("--- Blocking Mode ---")
    start = time.perf_counter()
    
    # 実際には同時に走らず、Task Aが終わるまでTask Bは始まらない
    await asyncio.gather(
        block_task("A", 2),
        block_task("B", 2)
    )
    
    # 合計時間は 2 + 2 = 4秒以上になる
    print(f"Total time: {time.perf_counter() - start:.2f} sec")

if __name__ == "__main__":
    asyncio.run(main_blocking())