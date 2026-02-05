# FastAPIの疑問

## websocket引数はどこから来るのか？
```python
@app.websocket("/ws")
async def echo_endpoint(websocket: WebSocket): <-これ、この引数！
```

### A: FastAPIが生成し、勝手に渡している

- これを「依存性の注入（Dependency Injection）と呼ぶ」
1. 接続検知: クライアントから/wsにアクセスが来る。
2. 解析: FastAPIは「このURLに対応するのは`echo_endpoint`だな」と判断する
3. 生成: 型ヒント `websocket: WebSocket`を見て、「あ。この関数はWebSocketの接続オブジェクトを欲しがっているな」と理解し、通信用のオブジェクトを生成する。
4. 注入（実行）: 生成したオブジェクトを引数に入れて、`echo_endpoint(生成したオブジェクト)`を実行する。

以上のプロセスで、websocket引数は自動で注入されている。

## `websocket. `系のメソッド

FastAPI（実態はStarletteというライブラリ）が提供する操作メソッド

- `await websocket.accept()`:
    - 受話器を取る。これやらんと通信が始まらない。
- `await websocket.receive_text()`:
    - 耳を澄ませば。相手が何かしゃべるまで、ここでプログラムが「一時停止」
- `await websocket.send_text("...")`:
    - しゃべる。相手にデータを送る
- `await websocket.close()`:
    - 通話を切る。動作終了

## `async with ... as websocket` とは

```python
async with websockets.connect(uri) as websocket:
```

これは２つの要素の組み合わせ
- `async with`（非同期コンテキストマネージャ）:
    - 「入るときに準備、出るときに片付け」を約束する構文。
    - 「ブロックに入ったら接続を開始し、ブロックを抜けたら（エラーが起きても正常終了しても） **自動的に切断（close）**する」という処理をしている
- `as websocket`:
    - 接続が成功して生成された「通信用オブジェクト」に`websocket`という変数名をつけて、ブロック内で使えるようにしている。

## なぜ`while True`？

### A: WebSocketは「電話（つなぎっぱなし）」だから

- HTTPの場合は`while`がない:
    - リクエストを受け取って->返事をして->終了

- WebSocketの場合、もし`while True`がないと？:
    1. `accept()` 接続
    2. `receive()` 一回受信
    3. `send()` 一回返信
    4. 終了
    - これじゃ全くWebSocketである意味がない
    - 無限ループで関数が終わらないようにして、常に`receive`で待ち構える必要がある。

## `if __name__ == "__main__":` とは？
Pythonの「お作法」。「直接実行されたときだけ動くガードマン」。

- `python client.py`とコマンドを叩いたとき:
    - `__name__`という特殊な変数には`"__main__"`という文字が入る
    - `if`の中身が実行される（クライアントが起動する）
- `import client`と他のファイルから読み込んだとき:
    - `__name__`には`"client"` という文字が入る
    - -> `if`の中身は無視される。

## `asyncio`とは？
### A: 「待ち時間」を有効に活用するための仕組み（非同期I/Oライブラリ）。
WebSocketやWeb通信は、処理時間のほとんどが「待ち時間（通信待ち）」。通常のプログラム（同期処理）だと、待っている間CPUがサボる
- 同期処理(Sync):
    - 「データ待ち（5秒） ... (CPU停止) ... 受信完了！次へ！」-> もっと働け
- 非同期処理(Async - asyncio):
    - 「データ待ち（5秒） ...よし、この待ち時間の間に別のタスクやったろ！...あ、受信完了したから戻ろ」->あまりにも優秀

`asyncio.run(...)`は、この「並行作業の管理監督（イベントループ）」を起動するスイッチである。これがないと`async`と書かれた関数（コルーチン）は実行できない。

### でもmain.pyには`asyncio`無いよね？
#### 僕らがエンジンをかけるわけじゃない

- `client.py`の場合:
    - 僕らが自分で実行するスクリプト
    - 僕ら自身がエンジンキー（`asyncio.run()`）を持ってきて、エンジンをかけなきゃいけない
- `main.py`（FastAPI）の場合:
    - このコードは僕らじゃなくて`uvicorn`（Webサーバ）が読み込んで実行する
    - `uvicorn`というプログラムの内部で、すでに`asynio`がインポートされ、イベントループは回っている
    - 僕らが各`main.py`は回転しているエンジンに「あとから組み込まれるパーツ（危険か？）」に過ぎない->僕らがエンジンを用意する必要は無い。

- 重い計算 
    - IOバウンド（軽い・待ち時間）
        - ウェイターが厨房に注文を通したあと、料理ができるまで手ぶらで待っている時間
        - 具体例: `time.sleep()`, `websocket.receive()`,データベースへの問い合わせ、ファイルの読み書き
        - 特徴: CPUはひましている
        - asyncの出番: ひましている間になにか別のことしよう！->非同期処理
    - CPUバウンド（重い・計算中）
        - ウェイターが客席でキャベツの千切りを始めた状態
        - 具体例: forループを1億回回す、画像処理（リサイズなど）、AIの推論（Whisper, VAD, LLMの計算）<- これが重要
        - CPUが100％稼働している
        - キャベツを切っている間、ウェイターの手が完全に塞がる。新規の客が来ても（Websocket接続）千切りが終わるまで「いらっしゃいませ」すら言えない->サーバーのフリーズ
    - 結局どうすればいい？
        - メインのウェイター（EventLoop）:
            - WebSocketの送受信、軽いJSONのパース、司令塔業務だけやる。
            - これらは`async def`でかく
        - 別の作業員（ThreadPool/run_in_executor）:
            - VAD, Whisper, LLMなどの重い計算を裏でやる
            - これらは普通の`def`（同期関数）で書く
```python
# stt_engine.py (普通の関数でいい)
def detect_voice(self, audio):  # asyncつけない
    # 重い計算...
    return True

# websocket_server.py
import asyncio

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    loop = asyncio.get_running_loop()

    while True:
        # 1. 受信はウェイターの仕事 (IOバウンド)
        data = await websocket.receive_bytes()

        # 2. 重い計算は別スレッドに投げる！ (ここが run_in_executor)
        # 「detect_voiceを裏でやっておいて。終わったら起こして」と頼む
        is_speech = await loop.run_in_executor(None, stt.detect_voice, data)

        if is_speech:
            print("喋ってる！")
```
的な