"""
LLMのGPU使用状況を確認するテストスクリプト
"""

from llama_cpp import Llama
import os
import time

MODEL_PATH = "/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/models/llm/Qwen2.5-7B-Instruct-abliterated-v2.Q3_K_M.gguf"

def check_cuda_available():
    """CUDAが利用可能か確認"""
    try:
        import torch
        if torch.cuda.is_available():
            print(f"PyTorch CUDA: 利用可能")
            print(f"  デバイス数: {torch.cuda.device_count()}")
            print(f"  デバイス名: {torch.cuda.get_device_name(0)}")
            print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            return True
        else:
            print("PyTorch CUDA: 利用不可")
            return False
    except ImportError:
        print("PyTorch: インストールされていません（llama-cpp-pythonのCUDA確認に影響なし）")
        return None

def main():
    print("=" * 50)
    print("GPU使用状況テスト")
    print("=" * 50)

    # モデルファイル確認
    if not os.path.exists(MODEL_PATH):
        print(f"エラー: モデルが見つかりません: {MODEL_PATH}")
        return

    print(f"\nモデル: {os.path.basename(MODEL_PATH)}")
    print(f"サイズ: {os.path.getsize(MODEL_PATH) / 1024**3:.2f} GB")

    # CUDA確認
    print("\n--- CUDA環境確認 ---")
    check_cuda_available()

    # llama-cpp-pythonでのGPUテスト
    print("\n--- llama-cpp-python GPUロードテスト ---")
    print("(verbose=True でCUDA検出ログを出力)\n")

    try:
        start_time = time.time()
        llm = Llama(
            model_path=MODEL_PATH,
            n_gpu_layers=-1,  # 全層をGPUにオフロード
            n_ctx=512,        # テスト用に小さめのコンテキスト
            verbose=True
        )
        load_time = time.time() - start_time
        print(f"\nモデルロード時間: {load_time:.2f}秒")

        # 実際に推論を実行してGPU使用を確認
        print("\n--- 推論テスト ---")
        test_prompt = "Hello"

        max_tokens = 32
        start_time = time.time()
        _ = llm(test_prompt, max_tokens=max_tokens, echo=False)
        inference_time = time.time() - start_time

        # 推定速度（max_tokens分生成されたと仮定）
        tokens_per_sec = max_tokens / inference_time if inference_time > 0 else 0

        print(f"最大生成トークン数: {max_tokens}")
        print(f"推論時間: {inference_time:.2f}秒")
        print(f"推定速度: {tokens_per_sec:.1f} tokens/sec")

        # 結果判定
        print("\n" + "=" * 50)
        print("判定結果")
        print("=" * 50)
        print("\n【GPUが使用されている場合のサイン】")
        print("・'ggml_cuda_init: found X CUDA devices' が表示される")
        print("・'offloaded X/Y layers to GPU' でXが0より大きい")
        print("・'BLAS = 1' が表示される")
        print("・推論速度が 10+ tokens/sec 以上")

        if tokens_per_sec > 10:
            print(f"\n推論速度 {tokens_per_sec:.1f} tokens/sec → GPUが使用されている可能性が高い")
        else:
            print(f"\n推論速度 {tokens_per_sec:.1f} tokens/sec → CPUのみの可能性あり（上記ログを確認）")

    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        print("\nトラブルシューティング:")
        print("・llama-cpp-pythonがCUDA対応でインストールされているか確認")
        print("  pip uninstall llama-cpp-python")
        print("  CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python --no-cache-dir")

if __name__ == "__main__":
    main()