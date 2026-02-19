import aiohttp
import asyncio
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv, find_dotenv
import os
import io
import re
from scipy.io import wavfile
import torch
from qwen_tts import Qwen3TTSModel
import argparse
from pathlib import Path
import numpy

REF_AUDIO = str(Path(__file__).resolve().parent.parent / "test" / "tts_reference" / "clone_data.wav")

load_dotenv(find_dotenv())

AZURE_API=str(os.getenv("AZURE_API2"))
REF_TEXT=str(os.getenv("REF_TEXT"))


class TTSEngine:
    def __init__(self, backend: str = "voicevox", host="localhost", port=50021, speaker_id=46):
        self.backend = backend
        if backend == "voicevox":
            self.base_url = f"http://{host}:{port}"
            self.speaker_id = speaker_id
            self.speedScale = 1.3
            self.pitchScale = 0.0
            self.volumeScale = 1.0
            self.intonationScale = 1.0
        elif backend == "qwen":
            self.qwen_model = Qwen3TTSModel.from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                device_map="auto",
                dtype=torch.bfloat16,
                )
            self.prompt_items = self.qwen_model.create_voice_clone_prompt(
                ref_audio=REF_AUDIO,
                ref_text=REF_TEXT,
                x_vector_only_mode=False, # Trueで話者の声質のみを適用する
            )
            print("Qwen TTS model and prompt loaded!")
        elif backend == "azure":
            self.speech_config = speechsdk.SpeechConfig(subscription=AZURE_API, region="japaneast")
            self.speech_config.speech_synthesis_voice_name = "ja-JP-NanamiNeural"
            self.speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
            )

    def _preprocess_for_ssml(self, text: str) -> str:
        """TTS用のテキスト前処理: 読み上げに不適切な記号をSSMLタグに変換"""
        # 「……」「…」「...」→ 無音ポーズに変換（「てんてんてん」と読まれるのを防ぐ）
        text = re.sub(r'……|…|\.{3,}', '<break time="500ms"/>', text)
        return text
    
    def set_seed(self, seed: int):
        """Qwenの再現性のためにseedを固定する"""
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    
    def qwen_synthesize(self, text: str, seed: int = 1) -> bytes | None:
        """Qwenを用いた音声合成"""
        self.set_seed(seed)

        wavs, sr = self.qwen_model.generate_voice_clone(
            text=text,
            language="Japanese",
            voice_clone_prompt=self.prompt_items,
            temperature=0.1,
            non_streaming_mode=True
        )
        # wavsはnumpy配列のリストで返ってくるので、最初の要素を使う
        wav = wavs[0]
        # numpy配列をbytesに変換して返す。ただし24khz16bitモノラルのPCM形式で返す。32768.0倍する
        wav = wav * 32768.0 # / numpy.max(numpy.abs(wav)) ノイズが発生
        n = int(sr * 0.01)  # 最後の10msをフェードアウト
        wav[-n:] *= numpy.linspace(1, 0, n)  # 最後のnサンプルをフェードアウトしてノイズを減らす
        with io.BytesIO() as buf:
            wavfile.write(buf, sr, wav.astype('int16'))
            return buf.getvalue()

    def azure_synthesize(self, text: str) -> bytes | None:
        """Azureを用いた音声合成"""
        text = self._preprocess_for_ssml(text)

        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=None
            )
        ssml = f"""
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="ja-JP">
  <voice name="ja-JP-NanamiNeural">
    <mstts:express-as style="chat">
      <prosody pitch="20%" rate="1.1">
        {text}
      </prosody>
    </mstts:express-as>
  </voice>
</speak>
"""
        result = synthesizer.speak_ssml_async(ssml).get()

        # check result
        if result:
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return result.audio_data
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                print(f"Canceled: {cancellation.reason}")
                print(f"Error details: {cancellation.error_details}")
            else:
                raise Exception("Speech synthesis failed: {}".format(result.reason))

    async def synthesize(self, text: str) -> bytes | None:
        """VoiceVoxを用いた音声合成"""
        if not text:
            return None
        
        timeout = aiohttp.ClientTimeout(
            total=30, # 全体にかかる時間
            connect=5, # 接続にかかる時間
            sock_read=25 # レスポンスの読み取り
        )

        # print("Synthesizing...")
        try:
            query_payload = {"text": text, "speaker": self.speaker_id}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                r = await session.post(f"{self.base_url}/audio_query", params=query_payload)
                if r.status != 200:
                    print(f"Voicevox Error (Query): {await r.text()}")
                    return None
                query_data = await r.json()
                query_data["speedScale"] = self.speedScale
                query_data["pitchScale"] = self.pitchScale
                query_data["volumeScale"] = self.volumeScale
                query_data["intonationScale"] = self.intonationScale
                # 音声を合成
                synthesis_payload = {"speaker": self.speaker_id}
                # query_dataはJSONとしてBodyに含める
                r = await session.post(
                    f"{self.base_url}/synthesis",
                    params=synthesis_payload,
                    json=query_data
                )
                if r.status != 200:
                    print(f"Voicevox Error (Synthesis): {await r.text()}")
                    return None
                return await r.read()
        
        except asyncio.TimeoutError:
            print("TTS Timeout: VoiceVoxが応答しません")
            return None
        

