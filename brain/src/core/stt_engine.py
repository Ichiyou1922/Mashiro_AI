from faster_whisper import WhisperModel
import torch
import torchaudio
import numpy as np
from dotenv import load_dotenv
import os
from groq import Groq
import io
from scipy.io import wavfile

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API")

class STTEngine:
    def __init__(self, model_size="small", device="cuda"):
        print("Loading VAD Model")

        # Whisperモデル用のデバイス設定（faster-whisperが内部で使用）
        self.whisper_device = device
        print(f"Whisper running on: {self.whisper_device}")

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

        # スレッド競合を避けるため、VAD用とWhisper用で別インスタンスを持つ
        # 両方ともCPU上に配置（GPU転送オーバーヘッドを回避）
        # - VADはCPU(ONNX)で動作するため、GPU経由は無駄
        # - Whisperへの入力はnumpy(CPU)なので、GPU経由は無駄
        self.vad_resampler = torchaudio.transforms.Resample(48000, 16000)
        self.whisper_resampler = torchaudio.transforms.Resample(48000, 16000)

        self.client = Groq(
            api_key=GROQ_KEY
        )

        self.hallucinationTexts = [
            "ご視聴ありがとうございました",
            "Thanks for watching",
            "저는 곤닉쳐고요",
            "좋아서 예쁘다",
            "아",
            " 예 오전주경고가 있었다면 노이 프로젝트가 어른다고",
            "Thank you.",
            "Thank you!",
        ]
        '''
        loadedObject = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=self.USE_ONNX,
            trust_repo=True)
        
        self.vad_model, utils = loadedObject
        
        (get_speech_timestamps,
         save_audio,
         read_audio,
         VADIterator,
         collect_chunks) = utils
         '''
        
        print(f"Loading Whisper Model ({model_size}...)")

        conpute_type = "int8" if device == "cpu" else "float16"

        loaded_whisper_obj = WhisperModel(model_size, device, compute_type=conpute_type)
        self.whisper_model = loaded_whisper_obj
    
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
    
    # .cpu().numpy()でテンソルを剥がしてndarrayを渡す
    def transcribe(self, audio_data: np.ndarray) -> str:
        """音声認識"""
        audio_data = audio_data
        segments, info = self.whisper_model.transcribe(
            audio_data,
            beam_size=5,
            language="ja",
            condition_on_previous_text=False,
            vad_filter=True,
            no_speech_threshold=0.6
        )
        text = ""
        for segment in segments:
            if segment.no_speech_prob > 0.6:
                continue
            text += segment.text
        if text in self.hallucinationTexts:
            return ""
        else:
            return text.strip()
        
    def groq_transcribe(self, discord_data: bytes) -> str:
        """groqAPIを使用した音声認識"""
        tensor_data = self.convert_for_whisper(discord_data)
        int_data = (tensor_data * 32767).astype(np.int16)
        bytesio = io.BytesIO()
        wavfile.write(bytesio, 16000, int_data)
        bytesio.seek(0)
        
        transcription = self.client.audio.transcriptions.create(
            file=("audio.wav", bytesio, "ausio/wav"),
            model="whisper-large-v3",
            prompt="Specify context or spelling",   
            response_format="json",                 
            language="ja",                          
            temperature=0.0                         
        )

        return transcription.text
    
