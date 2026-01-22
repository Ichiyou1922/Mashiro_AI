import aiohttp
import asyncio


class TTSEngine:
    def __init__(self, host="localhost", port=50021, speaker_id=14):
        self.base_url = f"http://{host}:{port}"
        self.speaker_id = speaker_id

    async def synthesize(self, text: str) -> bytes | None:
        """音声合成"""
        if not text:
            return None
        print("Synthesizing...")
        try:
            query_payload = {"text": text, "speaker": self.speaker_id}
            async with aiohttp.ClientSession() as session:
                r = await session.post(f"{self.base_url}/audio_query", params=query_payload)
                if r.status != 200:
                    print(f"Voicevox Error (Query): {await r.text()}")
                    return None
                query_data = await r.json()
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

        except Exception as e:
            print(f"TTS Error: {e}")
            print("Docker VoiceVoxが起動しているかチェック！")
            return None

