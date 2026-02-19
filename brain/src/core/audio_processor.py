import librosa
import numpy as np
import scipy.io.wavfile as wavfile
import io

class AudioProcessor:
    def __init__(self):
        self.n_steps = -2.0

    def _bytes_to_nparray(self, wave_audio: bytes) -> tuple[int, np.ndarray]:
        """Bytes形式の音声データをnumpyのndarrayに変換する"""
        sr, audio = wavfile.read(io.BytesIO(wave_audio))
        audio = audio.astype(np.float32) / 32768.0 # int16からfloat32に変換
        return sr, audio
    
    def pitch_shift(self, audio_array: np.ndarray, sr: int, n_steps: float=0.0) -> np.ndarray:
        """音声のピッチをn_steps分シフトする"""
        if n_steps is None:
            n_steps = self.n_steps
        return librosa.effects.pitch_shift(audio_array, sr=sr, n_steps=n_steps)
    
    def formant_shift(self, audio, sr, shift_amount):
        # STFT
        S = librosa.stft(audio, n_fft=2048, hop_length=512)
        mag, phase = np.abs(S), np.angle(S)
        # magnitudeの周波数ビンをシフト
        freq_bins = mag.shape[0]
        shift_bins = int(freq_bins * shift_amount * 0.1)

        # シフトしたmagnitudeを作成
        shifted_mag = np.zeros_like(mag)
        if shift_bins > 0:
            shifted_mag[shift_bins:] = mag[:-shift_bins]
            # ↓ 境界をスムーズにブレンド
            blend_region = min(shift_bins, 20)
            for i in range(blend_region):
                weight = i / blend_region
                shifted_mag[i] = mag[i] * (1 - weight)
        elif shift_bins < 0:
            shift_bins = abs(shift_bins)
            shifted_mag[:-shift_bins] = mag[shift_bins:]
            # ↓ 上端のエネルギーを残す
            shifted_mag[-shift_bins:] = mag[-shift_bins:] * 0.5

        # 元のPhaseと再結合 -> iSTFT
        S_shifted = shifted_mag * np.exp(1j * phase)
        return librosa.istft(S_shifted, hop_length=512, length=len(audio))
    
    def _nparray_to_bytes(self, audio_array: np.ndarray, sr: int = 24000) -> bytes:
        """numpyのndarrayをBytes形式の音声データに変換する"""
        buf = io.BytesIO()
        wavfile.write(buf, sr, (audio_array * 32768).astype(np.int16)) # float32からint16に変換して書き込み

        return buf.getvalue()
    
    def process(self, wav_bytes: bytes, formant_shift_amount: float = -0.1) -> bytes:
        sr, audio = self._bytes_to_nparray(wav_bytes)
        #audio = self.formant_shift(audio, sr, formant_shift_amount)
        audio = self.pitch_shift(audio, sr, n_steps=self.n_steps)
        return self._nparray_to_bytes(audio, sr)