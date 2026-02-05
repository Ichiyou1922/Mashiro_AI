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

- voicevoxの起動
- cpu版
```bash
 docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest 
```

- gpu版
```bash
 docker run --rm --gpus all -p 50021:50021 voicevox/voicevox_engine:nvidia-ubuntu20.04-latest 

```
