# Discord DAVE プロトコル対応 修正レポート (2026-03-18)

## 問題の概要

`!join` コマンドでボイスチャンネルに参加しようとすると、Discordの音声通話に一瞬参加してすぐ切断される。

## 根本原因

2026年3月2日以降、DiscordはすべてのクライアントにDAVE (Discord Audio/Video End-to-End Encryption) プロトコルのサポートを必須化した。

- `discord.py 2.6.4` はDAVE未対応 → close code **4017** (`E2EE/DAVE protocol required`) で5回リトライ後に静かに失敗
- `discord-ext-voice-recv 0.5.2a179` (アルファ版) もDAVE未対応 → 受信した暗号化音声パケットをそのままopusデコードしようとしてクラッシュ

## 修正内容

### 1. discord.py 2.6.4 → 2.7.1 へアップグレード + davey インストール

```
pip install discord.py==2.7.1 davey==0.1.4
```

- discord.py 2.7.1 はDAVEハンドシェイク (MLS鍵交換) と音声送信のDAVE暗号化に対応
- `davey` はDAVE暗号化/復号のPythonバインディング

### 2. `brain/src/main.py` の修正

#### a) logging.basicConfig 追加 (DEBUGログの出力)
discord内部のDEBUGログが `logging.basicConfig()` なしでは出力されず捨てられていた。
voice_state, gateway 等のDEBUGログが出るように設定追加。

#### b) `_cleanup_voice()` の修正
```python
# 修正前: 接続失敗したvcがクリーンアップされない
if vc is not None and vc.is_connected():

# 修正後: force=Trueは未接続状態でも安全に動作する
if vc is not None:
```

#### c) `join` コマンドに接続失敗の検知を追加
`channel.connect()` 後に `vc.is_connected()` をチェックし、失敗時はクリーンアップ + エラーメッセージを返して早期リターン。

### 3. `brain/src/audiosink.py` の修正 (最重要)

voice_recvのPacketRouterがDAVE暗号化パケットのopusデコードに失敗してクラッシュする問題を、ライブラリ非改変で解決。

#### a) `wants_opus() = True`
PacketRouterのopusデコードをスキップさせ、トランスポート復号済みの生データをそのままwrite()に渡す。

#### b) `_dave_decrypt()` メソッド追加
- `vc._connection.dave_session` を使ってDAVE復号
- 復号失敗時は `set_passthrough_mode(True, 50)` でリトライ (DAVE遷移期間の対応)
- 完全に失敗した場合は生データをフォールバックとして返す

#### c) 自前opus decode
ユーザーごとに `discord.opus.Decoder()` インスタンスを保持し、DAVE復号後のデータを自前でPCMに変換。OpusErrorはスキップして接続を維持。

## 修正前後の音声受信フロー

```
修正前 (voice_recv内部):
  UDPパケット → トランスポート復号 → opus decode → write(pcm)
  (DAVEサプリメンタルデータが混入 → OpusError → PacketRouterクラッシュ → 切断)

修正後 (audiosink.py内):
  UDPパケット → トランスポート復号 → write(raw)
    → _dave_decrypt() でDAVE復号 (サプリメンタルデータ除去)
    → discord.opus.Decoder.decode() でPCM変換
    → OpusError時はスキップ (接続維持)
```

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `brain/src/main.py` | logging設定, _cleanup_voice修正, join接続失敗検知 |
| `brain/src/audiosink.py` | wants_opus=True, _dave_decrypt(), 自前opus decode |

## 依存パッケージの変更

| パッケージ | 変更前 | 変更後 |
|---|---|---|
| discord.py | 2.6.4 | 2.7.1 |
| davey | (なし) | 0.1.4 |
| discord-ext-voice-recv | 0.5.2a179 | 0.5.2a179 (変更なし) |

## 残存する問題

1. **オーディオインターフェイス経由のマイク**: PCマイク直接は認識するが、オーディオインターフェイス経由だとhallucination判定になる場合がある (品質/ゲインの問題の可能性)
2. **応答速度**: 以前より遅くなった可能性がある (要調査)
3. **DAVE passthrough fallback**: 一部パケット (全体の約5%) でDAVE復号が失敗しpassthrough→OpusErrorでスキップされる。実用上は問題ないが完全ではない
4. **voice_recvのDAVE正式対応**: アルファ版ライブラリが正式にDAVE対応すれば、wants_opus/自前decodeのワークアラウンドは不要になる

## デバッグで判明した技術的詳細

- Discord voice WebSocket close code **4017** = `E2EE/DAVE protocol required`
- discord.py 2.6.4 の `channel.connect()` は5回リトライ後に **例外なしで** disconnected状態を返すバグがある
- DAVEサプリメンタルデータは各音声パケット末尾に約12バイト付加される (in=120B → out=108B)
- `davey.DaveSession.can_passthrough(user_id)` はper-user API (引数必須)
- `set_passthrough_mode(True, N)` は次のN回のdecrypt呼び出しでpassthroughを有効にする
