import requests


class TTSEngine:
    def __init__(self, host="localhost", port=50021, speaker_id=14):
        self.base_url = f"http://{host}:{port}"
        self.speaker_id = speaker_id

    def synthesize(self, text) -> bytes:
        """音声合成"""
        if not text:
            return  
        print("Synthesizing...")
        try:
            query_payload = {"text": text, "speaker": self.talkerId}
            r = requests.post(f"{self.URL}/audio_query", params=query_payload)
            if r.status_code != 200:
                print(f"Voicevox Error (Query): {r.text}")
                return
            query_data = r.json()
             
            # 音声を合成
            synthesis_payload = {"speaker": self.talkerId}
            # query_dataはJSONとしてBodyに含める
            r = requests.post(
                f"{self.URL}/synthesis",
                params=synthesis_payload,
                json=query_data
            )
            if r.status_code != 200:
                print(f"Voicevox Error (Synthesis): {r.text}")
            return r.content

        except Exception as e:
            print(f"TTS Error: {e}")
            print("Docker VoiceVoxが起動しているかチェック！")

ttsEngine = TTSEngine("http://localhost:50021", 14)