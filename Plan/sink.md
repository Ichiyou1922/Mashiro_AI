graph TD
    User[ユーザーの声] -->|UDP Packet| Discord[Discord Gateway]
    Discord -->|Opus Encoded| Bot[Main.py / VoiceRecv]
    Bot -->|Decode| Sink[AudioSink (受信クラス)]
    
    subgraph "Sink内部 (ここを実装する)"
        Sink -->|write(user, data)| Buffer[一時保存バッファ]
        Buffer -->|一定量溜まった?| Check{Yes}
        Check -->|run_in_executor| STT[STTEngine]
    end
    
    STT -->|Text| LLM[LLMEngine]