# Mashiro_AI

- PyTorch(CUDA)のインストール

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

- llama-cpp-python(LLM)のインストール(GPUサポート)

```bash
# キャッシュを無視して再ビルド・インストール
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade
```

- faster-whisperのインストール

```bash
pip install faster-whisper
```

- requirements.txtの内容通りインストール

```bash
pip install -r requirements.txt
```

