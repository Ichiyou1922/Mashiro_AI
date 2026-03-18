from faster_whisper import WhisperModel
import torch
import torchaudio
import numpy as np
from dotenv import load_dotenv
import os
from groq import Groq
import io
from scipy.io import wavfile
from .vad_engine import VADEngine

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API")

class STTEngine:
    def __init__(self, model_size="small", device="cuda", model="groq"):
        if model == "whisper":
            print("Loading VAD Model")

            # Whisperモデル用のデバイス設定（faster-whisperが内部で使用）
            self.whisper_device = device
            print(f"Whisper running on: {self.whisper_device}")

            # スレッド競合を避けるため、VAD用とWhisper用で別インスタンスを持つ
            # 両方ともCPU上に配置（GPU転送オーバーヘッドを回避）
            # - VADはCPU(ONNX)で動作するため、GPU経由は無駄
            # - Whisperへの入力はnumpy(CPU)なので、GPU経由は無駄
    
            print(f"Loading Whisper Model ({model_size}...)")

            compute_type = "int8" if device == "cpu" else "float16"

            loaded_whisper_obj = WhisperModel(model_size, device, compute_type=compute_type)
            self.whisper_model = loaded_whisper_obj

        self.model = model

        self.client = Groq(
            api_key=GROQ_KEY
        )

        self.hallucinationTexts = {
            "ご視聴ありがとうございました",
            "Thanks for watching",
            "저는 곤닉쳐고요",
            "좋아서 예쁘다",
            "아",
            " 예 오전주경고가 있었다면 노이 프로젝트가 어른다고",
            "Thank you.",
            "Thank you!",
            "はい。",
            "またお会いしましょう。",
            "ご視聴ありがとうございました。",
            "ありがとうございました。",
            "おめでとうございます。"
            "おわり。"
            ""
        }

        self.vad = VADEngine()
    
    # .cpu().numpy()でテンソルを剥がしてndarrayを渡す
    def transcribe(self, audio_data: np.ndarray) -> str | None:
        """音声認識"""
        audio_data = audio_data
        segments, info = self.whisper_model.transcribe(
            audio_data,
            # word_timestamps=True,
            beam_size=5,
            language="ja",
            condition_on_previous_text=False,
            vad_filter=True,
            no_speech_threshold=0.6,
            initial_prompt="えーと、あー、うーん、そのーなどのフィラーを含めること" # フィラーの追加
        )
        text = ""
        for segment in segments:
            if segment.no_speech_prob > 0.6:
                continue
            text += segment.text
        if text in self.hallucinationTexts:
            return
        else:
            return text.strip()
        
    def groq_transcribe(self, discord_data: bytes) -> str | None:
        """groqAPIを使用した音声認識"""
        tensor_data = self.vad.convert_for_whisper(discord_data)
        int_data = (tensor_data * 32767).astype(np.int16)
        bytesio = io.BytesIO()
        wavfile.write(bytesio, 16000, int_data)
        bytesio.seek(0)

        transcription = self.client.audio.transcriptions.create(
            file=("audio.wav", bytesio, "audio/wav"),
            model="whisper-large-v3-turbo",
            prompt="えーと、あー、うーん等のフィラーも含めて書き起こしてください。「ましろ」という人名が出るので注意してください。",
            response_format="json",
            language="ja",
            temperature=0.0,

        )
        if transcription.text in self.hallucinationTexts:
            return

        return transcription.text.strip()
    
