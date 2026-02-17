Playwrightでwebゲームを操作する一般的なメソッド
カテゴリ1：ナビゲーション・待機

# ページ移動
await page.goto("https://...")

# 要素が現れるまで待つ（最重要）
await page.wait_for_selector(".game-board")

# 指定時間待つ
await page.wait_for_timeout(1000)  # 1秒

# ページ読み込み完了まで待つ
await page.wait_for_load_state("networkidle")

# カスタム条件が満たされるまで待つ（JavaScriptで条件式を書く）
await page.wait_for_function("document.querySelector('#status').textContent === 'Your Turn'")
カテゴリ2：要素取得・状態読み取り

# 1つ取得（なければNone）
el = await page.query_selector("#score")

# 複数取得（リスト）
cells = await page.query_selector_all(".cell")

# テキスト内容
text = await el.text_content()        # "X"

# 属性値
cls = await el.get_attribute("class") # "space c2 r2"
val = await el.get_attribute("data-value")

# HTML内容
html = await el.inner_html()

# 表示状態
visible = await el.is_visible()
enabled = await el.is_enabled()
カテゴリ3：操作

# クリック
await page.click(".cell")
await el.click()  # 要素オブジェクトからも可

# テキスト入力
await page.fill("input[name='player']", "ましろ")
await page.type("input", "text")  # 1文字ずつタイプ（より人間らしい）

# キーボード
await page.keyboard.press("Enter")
await page.keyboard.press("ArrowRight")
カテゴリ4：JavaScript実行（応用）

# ページのJSを直接実行（DOM操作の抜け道）
result = await page.evaluate("document.querySelector('#score').textContent")

# 複雑な状態の取得
board_state = await page.evaluate("""
    () => {
        const cells = document.querySelectorAll('.space');
        return Array.from(cells).map(c => c.textContent.trim());
    }
""")
カテゴリ5：DOM変化の待機（重要）
CPUの手番待ちなど、「何かが変化するまで待つ」のに使います：


# セルの数が変化するまで待つ（CPUが手を打った）
await page.wait_for_function("""
    () => document.querySelectorAll('.space:not(:empty)').length > prevCount
""")