import asyncio
import time
import concurrent.futures

# asyncio.sleep()のような「待ち」がない計算処理を非同期空間で扱いたい
# -> 別のスレッドやプロセスに逃がす
# 重いブロッキング処理（CPUバウンドな計算や、非同期対応していないライブラリの使用）
def heavy_blocking_function(x):
    print(f"Heavy calculation for {x} started")
    time.sleep(2)  # 重い処理のシミュレーション
    return x * x

async def main_executor():
    # 現在のイベントループ（現場監督）を呼び出す(get_running_loop)
    loop = asyncio.get_running_loop()
    
    print("--- Executor Mode ---")
    start = time.perf_counter()

    # ThreadPoolExecutorを使って、別のスレッドでブロッキング処理を実行させる
    # これによりメインのイベントループは止まらない
    # withを使うとブロックを抜けたときに自動でクリーンアップされる
    with concurrent.futures.ThreadPoolExecutor() as pool: # with A() as B: はA()を実行して準備が整った実態を、このブロック内ではBとして扱いますよ、という意味
        result = await asyncio.gather(
            loop.run_in_executor(pool, heavy_blocking_function, 10),
            loop.run_in_executor(pool, heavy_blocking_function, 20)
        )
        
    print(f"Results: {result}")
    print(f"Total time: {time.perf_counter() - start:.2f} sec")

if __name__ == "__main__":
    asyncio.run(main_executor())