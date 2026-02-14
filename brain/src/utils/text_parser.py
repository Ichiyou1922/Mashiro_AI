import re

def parse_emotion(text: str) -> tuple[str, str]:
    # 文末だけでなく、文中のどこにあっても検出するように変更
    match = re.search(r'\[([^\]]+)\]', text)

    if match:
        emotion_raw = match.group(1)
        # タグを除去
        clean_text = text[:match.start()] + text[match.end():]
        
        emotion = emotion_raw.lower() # 一応小文字化

        # マッピング
        if emotion in ["neutral", "happy", "sad", "angry", "surprised", "shy", "sleepy", "bored", "question", "wink"]:
            pass # そのまま

        elif emotion in ["excited", "joy"]:
            emotion = 'happy'

        elif emotion in ["request", "doubt", "confused"]:
            emotion = 'question'

        elif emotion in ["shocked", "grief"]:
            emotion = 'sad'

        elif emotion in ["tired"]:
            emotion = 'sleepy'

        elif emotion in ["goal"]:
            emotion = 'happy'

        elif emotion in ["annoyed"]:
            emotion = 'angry'
            
        else:
            # 知らないタグだった場合はneutralにするか、あるいはエラー回避でneutral
            emotion = 'neutral'
    else:
        emotion = 'neutral'
        clean_text = text
    
    return (clean_text, emotion)