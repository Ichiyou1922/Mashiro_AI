import re

def parse_emotion(text: str) -> tuple[str, str]:
    match = re.search(r'\[([^\]]+)\]$', text)

    if match:
        emotion = match.group(1)
        clean_text = text[:match.start()] + text[match.end():]
        if emotion in ["neutral", "happy", "sad", "angry", "surprised", "shy", "sleepy", "bored", "question"]:
            emotion = emotion

        elif emotion in ["excited"]:
            emotion = 'happy'

        elif emotion in ["request", "doubt", "confused"]:
            emotion = 'question'

        elif emotion in ["shocked"]:
            emotion = 'sad'

        elif emotion in ["tired"]:
            emotion = 'sleepy'

        elif emotion in ["goal"]:
            emotion = 'happy'

        elif emotion in ["annoyed"]:
            emotion = 'angry'
            
        else:
            emotion = 'neutral'
    else:
        emotion = 'neutral'
        clean_text = text
    
    parsed_tuple = (clean_text, emotion)
    return (parsed_tuple)