# DAVE修正の技術的負債を解消するための学習ガイド

この資料は、2026-03-18のDAVE対応修正を**自分で理解し、将来自分で修正・改善できるようになる**ための学習ガイドです。

---

## 目次

1. [全体像: 音声パケットの旅](#1-全体像-音声パケットの旅)
2. [暗号化の2層構造](#2-暗号化の2層構造)
3. [voice_recvライブラリの内部構造](#3-voice_recvライブラリの内部構造)
4. [ワークアラウンドの仕組み](#4-ワークアラウンドの仕組み)
5. [Opusコーデックの基礎](#5-opusコーデックの基礎)
6. [理解度チェック](#6-理解度チェック)
7. [将来このワークアラウンドを外すとき](#7-将来このワークアラウンドを外すとき)

---

## 1. 全体像: 音声パケットの旅

Discord VCで誰かが喋ると、その音声は以下の経路をたどってましろに届きます：

```
発話者のマイク
  ↓ PCM (生の音声波形データ)
Discordクライアント: Opus圧縮
  ↓ Opusフレーム (~120バイト)
Discordクライアント: DAVE暗号化 (E2EE)
  ↓ DAVE暗号化データ (Opusフレーム + 12バイトの付加データ)
Discordクライアント: トランスポート暗号化
  ↓ 暗号化RTPパケット
Discord音声サーバー (中継のみ、復号しない)
  ↓ 暗号化RTPパケット
ましろのBot: トランスポート復号
  ↓ DAVE暗号化データ
ましろのBot: DAVE復号   ← ★ 今回追加した部分
  ↓ Opusフレーム
ましろのBot: Opus復号   ← ★ 今回自前で行うようにした部分
  ↓ PCM (生の音声波形データ)
VAD → STT → LLM → TTS
```

### 考えてみよう

> Q1: なぜDiscordサーバーは音声データを復号しないのか？ E2EE (End-to-End Encryption) の「End-to-End」とは何を意味している？

> Q2: もしDAVE復号をスキップしてOpusデコードしたら何が起きる？ 120バイトのOpusデータに12バイトの余計なデータがついた状態を想像してみよう。

---

## 2. 暗号化の2層構造

### 2.1 トランスポート暗号化 (Transport Encryption)

**目的**: Botと音声サーバー間の通信を保護する。

```
暗号方式: aead_xchacha20_poly1305_rtpsize (現在のDiscord標準)
鍵の共有: voice WebSocketで交換 (secret_key)
復号する場所: voice_recvライブラリの PacketDecryptor
該当コード: brain/.venv/.../voice_recv/reader.py の PacketDecryptor クラス
```

これは**以前から存在していた**暗号化で、voice_recvが対応済み。

### 2.2 DAVE暗号化 (Discord Audio/Video E2EE)

**目的**: 音声サーバーすらも音声を聞けないようにする (真のE2EE)。

```
暗号方式: MLS (Messaging Layer Security) ベースの鍵交換 + 独自フレーム暗号化
鍵の共有: voice WebSocketのDAVEハンドシェイク (discord.py 2.7.1が処理)
復号する場所: davey ライブラリの DaveSession.decrypt()
該当コード: brain/src/audiosink.py の _dave_decrypt() メソッド
```

これが**2026年3月2日から必須化**された暗号化。

### なぜ2層？

```
                     Bot ←→ 音声サーバー ←→ 他のユーザー

トランスポート暗号化:  [==保護==]              [==保護==]
                     (サーバーは復号可能)

DAVE暗号化:          [==============保護================]
                     (サーバーは復号不可能)
```

### 対応状況マトリクス

| コンポーネント | トランスポート暗号化 | DAVE暗号化 |
|---|---|---|
| discord.py 2.7.1 | 対応 (送信側) | 対応 (送信側のハンドシェイク+暗号化) |
| voice_recv 0.5.2a | 対応 (受信側の復号) | **未対応** (受信側の復号) |
| davey 0.1.4 | - | 対応 (受信側の復号API) |
| audiosink.py (自前) | - | daveyを呼び出して復号 |

### 考えてみよう

> Q3: voice_recvはトランスポート復号まではできる。しかしDAVE復号はできない。この状態でOpusデコードしようとするとどうなるか？

> Q4: `_dave_decrypt()` で `dave_session` が `None` の場合、データをそのまま返している。これはどういう状況で起きうるか？ そのとき音声は正常に聞こえるか？

---

## 3. voice_recvライブラリの内部構造

### 3.1 パケットの流れ (ライブラリ内部)

```
UDPソケット
  ↓ callback() [reader.py L136]
PacketDecryptor.decrypt_rtp()  ← トランスポート復号
  ↓ packet.decrypted_data に復号済みデータを格納
PacketRouter.feed_rtp()
  ↓
  ├─ wants_opus=False の場合: opus.Decoder.decode() → PCMとしてwrite()に渡す
  │                           ★ DAVE暗号化データをOpusとして解釈 → クラッシュ！
  │
  └─ wants_opus=True の場合:  そのままwrite()に渡す (decodeしない)
                              ★ 自分でDAVE復号 → Opusデコードできる！
```

### 3.2 重要なファイルと役割

```
reader.py
├── AudioReader        ← 全体のオーケストレーター
├── PacketDecryptor    ← トランスポート復号
├── SpeakingTimer      ← 発話開始/終了イベント
└── UDPKeepAlive       ← 接続維持

router.py
├── PacketRouter       ← RTPパケットの処理 + Opusデコード
└── SinkEventRouter    ← イベントの配送

sinks.py
└── AudioSink          ← 基底クラス (自分のMyAudioSinkの親)
```

### 3.3 `wants_opus()` の意味

AudioSinkの基底クラスには `wants_opus()` メソッドがある（デフォルトは `False`）。

```python
# wants_opus() = False (デフォルト)
# → PacketRouterがOpusデコードしてPCMをwrite()に渡す
# → data.pcm に PCMデータが入る

# wants_opus() = True
# → PacketRouterはOpusデコードをスキップ
# → data.packet.decrypted_data に「トランスポート復号済み」のデータが入る
# → data.pcm は None
```

これは本来「生のOpusデータが欲しいSink」のための機能だが、
今回は「PacketRouterにデコードさせるとクラッシュするから迂回する」ために使っている。

### 考えてみよう

> Q5: `reader.py` の `callback()` メソッド (L136-186) を読んでみよう。パケットが届いてから `PacketRouter.feed_rtp()` に渡されるまでの流れを追えるか？

> Q6: もしvoice_recvがDAVEに正式対応したら、`wants_opus()` を `False` に戻すだけで動くだろうか？ 他に何を変える必要がある？

---

## 4. ワークアラウンドの仕組み

### 4.1 `_dave_decrypt()` の詳細

```python
def _dave_decrypt(self, user_id: int, data: bytes) -> bytes:
```

**入力**: トランスポート復号済みのデータ (DAVE暗号化されたOpusフレーム + 付加データ)
**出力**: 純粋なOpusフレーム

#### 処理フロー:

```
data (トランスポート復号済み、~120バイト)
  ↓
daveyがインストールされていない? → そのまま返す (暗号化なし環境用)
  ↓
dave_sessionが存在しない? → そのまま返す (ハンドシェイク未完了)
  ↓
dave_session.decrypt(user_id, MediaType.audio, data) を試行
  ↓
成功 → 復号済みOpusデータを返す (~108バイト、12バイト減)
  ↓
失敗 → set_passthrough_mode(True, 50) でリトライ
  ↓
それでも失敗 → 元データをそのまま返す (フォールバック)
```

#### `set_passthrough_mode(True, 50)` とは？

DAVE暗号化には**遷移期間**がある。通話中にメンバーが入退室すると鍵が更新される。
この更新中、一部のパケットは暗号化されていない状態で届くことがある。

- `passthrough_mode` = 暗号化されていないパケットもそのまま通す
- `50` = 次の50回のdecrypt呼び出しで有効

### 4.2 自前Opusデコード

```python
pcm = self.user_data[user_key]["opus_decoder"].decode(opus_data, fec=False)
```

- ユーザーごとに独立した `Decoder` インスタンスを保持
- OpusはステートフルなCodec: デコーダーは直前のフレームの状態を記憶している
- だからユーザーごとに分ける必要がある

#### `fec=False` とは？

FEC (Forward Error Correction) = 前方誤り訂正。Opusはパケット紛失時に
次のパケットから前のフレームを復元する機能がある。`False` = 使わない。

### 考えてみよう

> Q7: なぜOpusデコーダーはユーザーごとに分ける必要がある？ もし全ユーザーで共有したらどうなる？ (ヒント: Opusはステートフル)

> Q8: `_dave_decrypt()` の最後のフォールバック (`return data`) で元データをそのまま返している。この場合、直後の `opus.Decoder.decode()` は成功するか？ 失敗するとしたら何が起きるか？

---

## 5. Opusコーデックの基礎

### 5.1 Discord音声のフォーマット

```
Opus設定:
  サンプリングレート: 48000 Hz
  チャンネル数: 2 (ステレオ)
  フレーム長: 20ms

PCM (復号後):
  1フレーム = 48000 × 2ch × 2bytes(int16) × 0.02秒 = 3840 バイト

Opus (圧縮):
  1フレーム ≈ 60〜160 バイト (可変長、内容による)
```

### 5.2 PCMからSTTまでの変換

```
Opus復号後のPCM: 48kHz, ステレオ, int16
        ↓ discord_to_silero() / convert_for_whisper()
VAD/STT用: 16kHz, モノラル, float32

変換内容:
1. ステレオ → モノラル (2ch平均)
2. 48kHz → 16kHz (リサンプリング、データ量1/3)
3. int16 → float32 (正規化、-1.0〜1.0の範囲)
```

### 5.3 なぜDAVE付加データでクラッシュするか

```
正常な Opusフレーム:   [ヘッダ][圧縮音声データ]  (108バイト)
DAVE付加あり:         [ヘッダ][圧縮音声データ][DAVE付加12バイト]  (120バイト)

Opusデコーダーの視点:
「120バイトのOpusフレームだな」→ 途中から意味不明なデータ → OpusError
```

Opusはバイナリフォーマットなので、末尾に余計なデータがあると
フレーム長の計算が合わなくなり、`corrupted stream` エラーになる。

### 考えてみよう

> Q9: `vad_engine.py` の `discord_to_silero()` を読んでみよう。48kHz→16kHzの変換はどのライブラリのどの関数で行っているか？

> Q10: PCM 3840バイトが20msの音声に相当する。1秒分のPCMデータは何バイトか？ (48kHz × 2ch × 2bytes × 1秒)

---

## 6. 理解度チェック

以下の質問に答えられれば、今回の修正を理解できています。

### レベル1: 何をしたか (What)

- [ ] 今回の修正でインストールしたパッケージは何か？
- [ ] `audiosink.py` に追加したメソッドは何か？
- [ ] `wants_opus()` の戻り値を何に変えたか？

### レベル2: どうやったか (How)

- [ ] 音声パケットがUDPソケットからPCMになるまでの流れを説明できるか？
- [ ] `_dave_decrypt()` の処理フローを説明できるか？
- [ ] なぜ `_cleanup_voice()` から `is_connected()` チェックを外したのか？

### レベル3: なぜそうしたか (Why)

- [ ] なぜ暗号化が2層あるのか？ それぞれの目的は？
- [ ] なぜvoice_recvライブラリを直接修正せず、`wants_opus()` で迂回したのか？
- [ ] なぜユーザーごとに独立したOpusデコーダーが必要なのか？
- [ ] `set_passthrough_mode(True, 50)` はどういう問題を解決しているか？

### レベル4: 代替案 (Alternatives)

- [ ] voice_recvがDAVEに正式対応したら、何を変更すればワークアラウンドを外せるか？
- [ ] Botではなく一般ユーザーとしてDiscordに接続するアプローチのメリット/デメリットは？
- [ ] OBS仮想デバイスを使うアプローチとの違いは？

---

## 7. 将来このワークアラウンドを外すとき

### 条件

`discord-ext-voice-recv` がDAVEに正式対応したとき。

### 手順

1. `audiosink.py`:
   - `wants_opus()` を `False` に戻す (または削除)
   - `_dave_decrypt()` を削除
   - `_get_opus_decoder()` を削除
   - `user_data` から `opus_decoder` を削除
   - `write()` 内の自前デコード処理を削除し、`data.pcm` を直接使うように戻す
   - `davey` のimportを削除

2. `main.py`:
   - DEBUGレベルのログ設定を必要に応じて削除

3. 依存パッケージ:
   - `davey` が不要になるか確認 (discord.pyのDAVE送信で使用している可能性あり)

### 確認方法

```
voice_recvのリリースノートで "DAVE" または "E2EE" の対応を確認
→ アップデート後、wants_opus=False で接続テスト
→ OpusErrorなくPCMが取れれば成功
```

---

## 参考リンク

- [Discord DAVE Whitepaper](https://daveprotocol.com/) - DAVE暗号化の公式仕様
- [discord.py Changelog](https://discordpy.readthedocs.io/en/stable/whats_new.html) - DAVE対応バージョン情報
- [Opus Codec](https://opus-codec.org/) - Opusの仕様と解説
- [MLS Protocol](https://messaginglayersecurity.rocks/) - DAVE内部で使われる鍵交換プロトコル
- [修正レポート](2026-03-18_dave_voice_fix_report.md) - 今回の修正の詳細記録
