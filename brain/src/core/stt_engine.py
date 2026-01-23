from faster_whisper import WhisperModel
import torch
import torchaudio
import numpy as np

class STTEngine:
    def __init__(self, model_size="small", device="cuda"):
        print("Loading VAD Model")

        # deviceを探索する
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")
        print(f"Running on: {self.device}")
        
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
        self.resampler = torchaudio.transforms.Resample(48000, 16000).to(self.device)
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
        loaded_whisper_obj = WhisperModel(model_size, device, compute_type="float16")
        self.whisper_model = loaded_whisper_obj
    
    # Discordから受け取った44100Hzのbytesを16000HzのTensorに変換し、モノラルに圧縮する
    def discord_to_silero(self, discord_data: bytes) -> torch.Tensor:
        # int16で読み込む。copy=Falseでメモリコピーを防ぐ
        audio_array = np.frombuffer(discord_data, dtype=np.int16).copy()
        # Tensorに変換して、Float32に正規化する
        # Int16の最大値 32768.0で割って、-1~1の範囲にする
        tensor_data = torch.from_numpy(audio_array).float() / 32768.0 # torch.from_numpyはゼロコピーで早い
        # ステレオ(Interleaved)を分離する
        # [L, R, L, R...] -> [samples, 2] -> [2, samples] (Channels first)
        # slicingは array[start:stop:step]の形
        left_channel = tensor_data[::2] # 左チャンネル
        right_channel = tensor_data[1::2] # 右チャンネル
        # .view(-1, 2) でデータを二列に並べ直す
        # モノラルにミックスダウン（平均）
        tensor_mono = (left_channel + right_channel) / 2.0
        # バッチ次元を追加 [samples] -> [1, samples] ：Resamplerのために
        tensor_mono = tensor_mono.unsqueeze(0)
        # デバイスに移動
        tensor_mono = tensor_mono.to(self.device)
        resampled_data: torch.Tensor = self.resampler(tensor_mono)
        result = resampled_data.squeeze()
        return result
        

    def detect_voice(self, audio_data: torch.Tensor) -> bool:
        """VADを使用した音声検出"""
        '''
        window_size_samples = 512
        for i in range(0, len(audio_data), window_size_samples):
            chunk = audio_data[i: i + window_size_samples]
            if len(chunk) < window_size_samples:
                break
            speech_prob = self.vad_model(chunk, self.SAMPLING_RATE).item()
            return speech_prob > 0.5
        '''
        speech_prob = self.vad_model(audio_data, self.SAMPLING_RATE).item()
        return speech_prob > 0.5
    
    # .cpu().numpy()でテンソルを剥がしてndarrayを渡す
    def transcribe(self, audio_tensor: torch.Tensor) -> str:
        """音声認識"""
        audio_data = audio_tensor.cpu().numpy()
        segments, info = self.whisper_model.transcribe(audio_data, beam_size=5)
        text = ""
        for segment in segments:
            text += segment.text
        return text.strip()
    
