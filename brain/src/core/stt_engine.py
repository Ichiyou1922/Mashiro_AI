from faster_whisper import WhisperModel
import torch
import numpy as np

class STTEngine:
    def __init__(self, model_size="small", device="cuda"):
        print("Loading VAD Model")
        torch.set_num_threads(1)
        
        self.vad_model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            trust_repo=True # 警告対策
        )
        (get_speech_timestamps, _, _, _, _) = utils
        print(f"Loading Whisper Model ({model_size}...)")
        self.model = WhisperModel(model_size, device, compute_type="float16")

    def detect_voice(self, audio_data: np.ndarray, sampling_rate=16000) -> bool:
        """VADを使用した音声検出"""
        audio_tensor = torch.from_numpy(audio_data.flatten())
        prob = self.vad_model(audio_tensor, sampling_rate).item()
        return prob > 0.5
    
    def transcribe(self, audio_data: np.ndarray) -> str:
        """音声認識"""
        segments, info = self.model(audio_data, beam_size=5)
        text = ""
        for segment in segments:
            text += segment.text
        return text.strip()
    
sttEngine = STTEngine("small", "cuda")