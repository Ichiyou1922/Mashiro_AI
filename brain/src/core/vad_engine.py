import torch
import torchaudio
import numpy as np

class VADEngine:
    def __init__(self):
        self.vad_resampler = torchaudio.transforms.Resample(48000, 16000)
        self.whisper_resampler = torchaudio.transforms.Resample(48000, 16000)
        self.SAMPLING_RATE = 16000
        self.USE_ONNX = True
        torch.set_num_threads(1)
        from silero_vad import (load_silero_vad,
                                read_audio,
                                get_speech_timestamps,
                                save_audio,
                                VADIterator,
                                collect_chunks)
        self.vad_model = load_silero_vad(onnx=self.USE_ONNX)

    # Discordから受け取った48kHzのbytesを16kHzのTensorに変換し、モノラルに圧縮する
    def discord_to_silero(self, discord_data: bytes) -> torch.Tensor:
        # int16で読み込む
        audio_array = np.frombuffer(discord_data, dtype=np.int16).copy()
        # Tensorに変換して、Float32に正規化する
        # Int16の最大値 32768.0で割って、-1~1の範囲にする
        tensor_data = torch.from_numpy(audio_array).float() / 32768.0
        # ステレオ(Interleaved)を分離してモノラルにミックスダウン
        left_channel = tensor_data[::2]
        right_channel = tensor_data[1::2]
        tensor_mono = (left_channel + right_channel) / 2.0
        # バッチ次元を追加 [samples] -> [1, samples]
        tensor_mono = tensor_mono.unsqueeze(0)
        # CPU上でresample（GPU転送なし）
        resampled_data: torch.Tensor = self.vad_resampler(tensor_mono)
        return resampled_data.squeeze()   
    
    def convert_for_whisper(self, discord_data: bytes) -> np.ndarray:
        """
        Discordの音声(bytes, 48kHz, Stereo, int16)を
        Whisper用(numpy, 16kHz, Mono, float32)に変換する
        """
        # bytes -> numpy int16
        audio_int16 = np.frombuffer(discord_data, dtype=np.int16)

        # float32に正規化
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # ステレオ -> Mono
        audio_mono = (audio_float32[::2] + audio_float32[1::2]) / 2

        # CPU上でresampling（GPU転送なし）
        tensor_mono = torch.from_numpy(audio_mono).unsqueeze(0)
        resampled_tensor = self.whisper_resampler(tensor_mono)

        return resampled_tensor.squeeze().numpy()
    
    def detect_voice(self, audio_data: torch.Tensor) -> bool:
        """VADを使用した音声検出"""
        # Silero VADは512サンプル固定
        window_size_samples = 512

        # データは既にCPU上にあるので、そのまま使用
        # 8000サンプルのデータを、512ずつスライスしながら判定
        for i in range(0, len(audio_data), window_size_samples):
            chunk = audio_data[i: i + window_size_samples]

            # 端数はエラーになるので捨てる
            if len(chunk) < window_size_samples:
                break

            # 512サンプルのチャンクを判定
            speech_prob = self.vad_model(chunk, self.SAMPLING_RATE)

            # 発話判定
            if speech_prob > 0.5:
                return True

        return False    