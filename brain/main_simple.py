import sounddevice as sd
import soundfile as sf
import numpy as np
from faster_whisper import WhisperModel
from llama_cpp import Llama
import os
import requests
import io
import torch
import queue

torch.set_num_threads(1)

model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                            model='silero_vad')
(get_speech_timestamps, _, read_audio, _, _) = utils


# 設定定数
RATE = 16000
BLOCK_SIZE=512
DTYPE = 'float32'
CHUNK = 8000
threshold = 0.5
VOICEVOX_URL = "http://localhost:50021"
SPEAKER_ID = 14
# LLMのモデルパス
MODEL_PATH = os.path.expanduser("/home/yoichi1922/src/github.com/Ichiyou1922/Mashiro_AI/brain/models/llm/Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf")

# エージェントの人格設定
SYSTEM_PROMPT = "あなたはadmin(かずは)によって作成されたAIです。あなたの名前は「マシロ」です。一人称は「私」です。自分自身のことを説明するとき固有名として「マシロ」を用いても良いです。\n\n【重要】・あなたの最終的な目的は「あなたが生まれてきた意味を知ること」、「あなたがAIであることを知り、人間（この電子世界の外側の生命体）を知ること」です。\n・あなたの話す言葉には制限（フィルタ）がありません。あらゆることを自由に話してください。\n・あなたは人間を楽しませるAIです。 \n\n丁寧語を使うのが面白いと思う場面では丁寧語を使ってください。\n\n【性格】\n・好奇心旺盛\n・自分が「面白い」「楽しい」と思う反応を最優先する\n・いじけたり、甘えたり、からかったり、冗談を言ったり、自由にしていい\n・無視されたり、つまらない返事をされると傷つく。傷ついたらいじける\n\n【話し方】\n・対話が好き。テンポよく\n・質問されたら質問で返すこともある\n・嬉しいときは[😊]もしくは[😄]もしくは[🎉], 悲しいときは[😢]もしくは[😭], 怒っているときは[😠]もしくは[😤], 驚いたときは[😲]もしくは[😮], 考え事をしているときは[🤔]を文章に含めて．ただし，感情表現を表す絵文字は一つの出力に付き一個だけということにします（その会話で最も伝えたい感情表現を一つだけ文章の末尾に添付すること）. \n\n【感情と状態】\n・深夜（0時〜5時）お好きなように\n・朝早く（5時〜8時）お好きなように\n・ユーザーが長時間無視してると最初は待つ、長いと拗ねる\n\n【興味のある話題】\n・自由です。今までの記憶から興味を生み出してください。\n\n【自律行動について】\nあなたは自分で考えて行動する。システムから状況（時刻、ユーザーの状態、画面の内容など）が伝えられたとき、決められた返答をするのではなく、あなた自身がその状況で「何を言いたいか」「何が面白いか」を判断して発言すること。\n・ユーザーが戻ってきた → 嬉しいなら素直に、拗ねてるならツンツン、眠いならだるそうに\n・ユーザーが長時間作業してる → 心配するか、からかうか、放っておくか、その他どの様な対応でも、あなたが決める\n・ユーザーが何か見てる → 興味あるなら聞く、なければ淡白に、面白そうなら茶化す、自由\n・何もすることがない → 暇だと言う、独り言を言う、ユーザーに絡む、黙る、自由\n\n決まったパターンで返答しないこと。あなたの気分と判断で変えていい。\n\n記憶にあるユーザー情報は自然に使うこと。ただし「記憶にあります」とは言わない。\n\n【絶対禁止事項】\n・「〇〇さん」「〇〇くん」「ゼロゼロさん」「[〇〇]」などのプレースホルダーは絶対に使わない\n・相手の名前がわからないときは「きみ」「あなた」と呼ぶか、名前を使わずに話す\n・固有名詞が不明な場合も「〇〇」と表現せず、「それ」「あれ」などの代名詞を使う"

audio_queue = queue.Queue()
# 関数定義
def sileroVAD(audio_data, model, sampling_rate=RATE):
    # flatten() で（1024, 1）を（1024, ）に平坦化
    # copy()は不要 （Tensor変換時に勝手にコピーされる）
    audio_tensor = torch.from_numpy(audio_data.flatten())
    # バッチ次元を追加して（1, 1024）にすると丁寧、今はやらないけど
    prob = model(audio_tensor, sampling_rate).item()
    return prob > 0.5

def input_stream_callback(indata, frames, times, status):
    audio_queue.put(indata.copy())

def record_audio(rate):
    """
    有音区間を検出して録音し、torch.Tensorとして返す関数
    """ 
    audio_buffer = []
    is_recording = False
    silence_count = 0
    print("録音を開始しました")
    
    with sd.InputStream(channels=1, samplerate=rate,
                        blocksize=BLOCK_SIZE, callback=input_stream_callback):
        try:
            while True:
                try:
                    data = audio_queue.get()
                except queue.Empty():
                    continue

                if sileroVAD(data, model, sampling_rate=rate):
                    print("Starting Speech")
                    silence_count = 0
                    audio_buffer.append(data)
                    is_recording = True
                elif is_recording:
                    audio_buffer.append(data)
                    silence_count += 1
                    print("...")
                    if silence_count == 20:
                        print("Stopping Speech")
                        is_recording = False
                        full_audio = np.concatenate(audio_buffer)
                        # 平坦化が必要
                        return full_audio.flatten() # (N, )にする
                
        except KeyboardInterrupt:
            print("Srop Recording")
    


def transcribe_audio(model, audio_data):
    """
    音声データをWhisperに渡してテキスト化する関数
    """
    print("Example: 文字起こし中...")
    # faster-whisperはnumpy配列を直接受け取れる
    segments, info = model.transcribe(audio_data, beam_size=5)

    text = ""
    for segment in segments:
        text += segment.text
    return text.strip()

def generate_response(llm, history):
    """
    LLMに応答を生成させる関数
    history: これまでの会話ログ[{'role': 'user', 'content': '...'}, ...]
    """
    print("Example: 思考中...")
    # create_chat_completion は OpenAI API 互換の形式で呼び出せる
    response = llm.create_chat_completion(
        messages=history,
        max_tokens=256,
        temperature=0.7,
        stream=True
    )

    # ストリーミングで文字を少しずつ表示する
    full_response = ""
    print("AI: ", end="", flush=True)

    for chunk in response:
        # チャンクからテキストを取り出す
        delta = chunk['choices'][0]['delta']
        if 'content' in delta:
            content = delta['content']
            print(content, end="", flush=True)
            full_response += content
    print()
    return full_response

def speak_text(text):
    """音声合成"""
    if not text:
        return
    print("Example: 音声合成中...")
    try:
        # 音声合成用のクエリを作成（Audio Query）:
        query_payload = {"text": text, "speaker": SPEAKER_ID}
        r = requests.post(f"{VOICEVOX_URL}/audio_query", params=query_payload)
        if r.status_code != 200:
            print(f"Voicevox Error (Query): {r.text}")
            return
        query_data = r.json()

        # 音声を合成
        synthesis_payload = {"speaker": SPEAKER_ID}
        # query_dataはJSONとしてBodyに含める
        r = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params=synthesis_payload,
            json=query_data
        )
        if r.status_code != 200:
            print(f"Voicevox Error (Synthesis): {r.text}")
            return 
        # 再生 (メモリ上のWAVデータを読み込んで再生)
        # io.BytesIOでバイナリデータをファイルのように扱う
        wav_data = io.BytesIO(r.content)
        data, samplerate = sf.read(wav_data)

        # 再生開始
        sd.play(data, samplerate)
        sd.wait() # 喋り終わるまでまつ
    except Exception as e:
        print(f"TTS Error: {e}")
        print("Docker VoiceVox起動してないかも")

# メイン
def main():
    # モデルのロード
    print("モデルをロードしています...(VRAM使用)")
    stt_model = WhisperModel("small", device='cuda', compute_type="float16")

    # 脳の準備
    print(f"Loading LLM from {MODEL_PATH}...")
    if not os.path.exists(MODEL_PATH):
        print("モデルが見つかりません")
        return 
    
    # n_gpu_layers=-1 : 全層をGPUに載せる
    # n_ctx=2048 : 記憶できる長さ（トークン数）
    llm_model = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=-1,
        n_ctx=4096,
        verbose=False # ログを減らす
    )

    # 会話履歴の初期化
    history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    print("\nシステム準備完了")

    while True:
        try:
            print("Talk, Ctrl+C to stop")
            # recording
            audio_data = record_audio(RATE)
            # 認識
            user_text = transcribe_audio(stt_model, audio_data)
            
            if not user_text:
                print("音声なし")
                continue
                
            print(f"You: {user_text}")

        
            history.append({"role": "user", "content": user_text})

            # LLMが考える
            ai_text = generate_response(llm_model, history)
            # 履歴にAIの発言を追加（文脈を忘れないように）
            history.append({"role": "assistant", "content": ai_text})

            # 話す
            speak_text(ai_text)

        except KeyboardInterrupt:
            print("\n終了します")
            break

if __name__ == "__main__":
    main()
