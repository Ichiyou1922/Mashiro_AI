# Memory Stream 導入計画

## 参考論文
- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) (Stanford, 2023)

---

## 1. 問題定義

### 現状の課題

| 課題 | 詳細 |
|------|------|
| 文脈破綻 | 単語レベルの類似度で検索するため、現在の文脈と異なる記憶がヒットする |
| コンテキスト汚染 | AIの変な回答が保存され、次回参照時に連鎖的に悪化する |
| 短期/長期の分離 | dequeとLanceDBが独立して動作し、統一的な検索ができない |
| 自律性の欠如 | AIが自発的に発話したり、行動を修正したりできない |

### 根本原因

```
現状: search_memory() = ベクトル類似度のみ
      ↓
関連性(relevance)しか考慮されていない
      ↓
新しさ(recency)や重要度(importance)が無視される
      ↓
古い/低品質な記憶が参照される
```

---

## 2. 解決策：Memory Stream アーキテクチャ

### 2.1 基本設計

```
┌──────────────────────────────────────────────────────────────────┐
│                    Memory Stream (LanceDB一本化)                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  観察/会話  │  観察/会話  │  Reflection  │  自己発話/計画   │  │
│  │ importance │ importance │   (統合)     │   (自律行動)    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│       score = α×recency + β×importance + γ×relevance            │
│                              ↓                                   │
│                        上位K件取得 → LLMへ                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 スコアリング式

```python
def calculate_retrieval_score(memory, query, current_time):
    # Recency: 指数減衰（最終アクセス時刻基準）
    hours_since_access = (current_time - memory.last_accessed) / 3600
    recency = math.exp(-0.99 * hours_since_access)

    # Importance: 0.0〜1.0 (正規化済み)
    importance = memory.importance

    # Relevance: ベクトル類似度（0.0〜1.0）
    relevance = cosine_similarity(query_vector, memory.vector)

    # 重み付け合計
    α, β, γ = 1.0, 1.0, 1.0
    score = α * recency + β * importance + γ * relevance

    return score
```

### 2.3 deque廃止

| 変更前 | 変更後 |
|--------|--------|
| deque(maxlen=10) で直近会話を保持 | 廃止 |
| LanceDBで長期記憶を検索 | 全記憶をLanceDBで統一管理 |
| 2つのシステムを別々に参照 | スコアリングで統一的に検索 |

---

## 3. 新しいスキーマ

### 3.1 Memory テーブル

```python
class Memory(LanceModel):
    # 既存フィールド
    vector: Vector(model.ndims()) = model.VectorField()
    text: str = model.SourceField()
    user_id: int
    user_name: str
    role: str                    # "interaction", "reflection", "self_talk"
    timestamp: float
    source: str

    # 新規フィールド
    importance: float = 0.0      # 0.0 = 未評価, 1-10 を正規化
    last_accessed: float = 0.0   # 最終参照時刻
    access_count: int = 0        # 参照回数
    is_reflection: bool = False  # Reflectionで生成された記憶か
    parent_ids: str = ""         # 統合元の記憶ID（カンマ区切り）
```

### 3.2 MemoryStore 新メソッド

```python
class MemoryStore:
    # 既存
    def add_memory(...)
    def search_memory(...)
    def get_recent(...)

    # 新規
    def search_with_score(self, query: str, limit: int = 10) -> list:
        """recency × importance × relevance でスコアリング検索"""

    def update_importance(self, memory_ids: list, scores: list):
        """バッチでimportance更新"""

    def get_pending_evaluation(self, limit: int = 30) -> list:
        """importance未評価の記憶を取得"""

    def rewrite_memory(self, memory_id: str, new_text: str):
        """汚染された記憶を書き換え"""

    def mark_accessed(self, memory_ids: list):
        """last_accessedとaccess_countを更新"""
```

---

## 4. Importance 評価

### 4.1 バッチ処理方式

```
会話1 → 保存（importance=0.0）
会話2 → 保存（importance=0.0）
...
会話N → 保存（importance=0.0）
        ↓
N件溜まったら（例: 30件）
        ↓
groq/gemini でまとめて評価
        ↓
importance 更新
        ↓
閾値チェック → Reflection発火？
```

### 4.2 評価プロンプト（案）

```
以下の会話記録それぞれについて、1〜10の重要度スコアをつけてください。

重要度の基準:
- 1-3: 日常的な挨拶、雑談
- 4-6: 一般的な情報交換、質問と回答
- 7-9: 個人的な情報、感情表現、重要な出来事
- 10: 人生の転機、深い信頼関係に関わる発言

会話記録:
1. "{text1}"
2. "{text2}"
...

JSON形式で回答: [{"id": 1, "score": 5}, ...]
```

### 4.3 人間フィードバック（ルールベース）

```python
NEGATIVE_KEYWORDS = ["やめて", "違う", "そうじゃない", "嫌い", "ちがう"]
POSITIVE_KEYWORDS = ["ありがとう", "すごい", "好き", "正解", "そうそう"]

def adjust_importance_by_feedback(user_message: str, prev_memory_id: str):
    for kw in NEGATIVE_KEYWORDS:
        if kw in user_message:
            decrease_importance(prev_memory_id, delta=-2)
            return
    for kw in POSITIVE_KEYWORDS:
        if kw in user_message:
            increase_importance(prev_memory_id, delta=+1)
            return
```

---

## 5. Reflection（内省）

### 5.1 トリガー条件

| 条件 | 詳細 |
|------|------|
| 自動 | importance合計が閾値（150）を超えたとき |
| 手動 | 管理画面からボタンで発火 |

### 5.2 プロセス

```
1. importance合計 > 150
        ↓
2. state = sleeping（アバター: 寝ている画像）
        ↓
3. 最新100件の記憶を取得
        ↓
4. groq/geminiに送信
   「これらの記憶から、重要なパターンや洞察を3〜5つ抽出してください」
        ↓
5. Reflection記憶として保存（is_reflection=True, importance=8）
        ↓
6. 汚染された記憶を検出・書き換え
        ↓
7. state = idle（起床）
        ↓
8. （オプション）夢の内容を話す
```

### 5.3 Reflectionプロンプト（案）

```
あなたは「ましろ」というAIキャラクターです。
以下は最近の記憶です。これらを振り返り、以下を行ってください：

1. 重要なパターンや洞察を3〜5つ抽出
2. 矛盾している記憶があれば指摘
3. 低品質な回答（オウム返し、文脈破綻）があれば修正案を提示

記憶:
{memories}

JSON形式で回答:
{
  "reflections": ["洞察1", "洞察2", ...],
  "contradictions": [{"id": "xxx", "reason": "..."}],
  "rewrites": [{"id": "xxx", "original": "...", "corrected": "..."}]
}
```

---

## 6. 自己発話機能

### 6.1 トリガー条件

| 条件 | 詳細 |
|------|------|
| 沈黙 | 一定時間（例: 30秒）発話がない |
| Reflection後 | 夢の内容を話す |
| 計画実行 | 予定していた行動を実行 |

### 6.2 実装案

```python
class SelfTalkManager:
    def __init__(self, llm_engine, silence_threshold=30):
        self.silence_threshold = silence_threshold
        self.last_activity = time.time()

    def check_and_speak(self):
        if time.time() - self.last_activity > self.silence_threshold:
            # 最近の記憶を取得
            recent = memory_store.get_recent(limit=5)

            # 文脈に応じて発話するか判断
            prompt = f"""
            最近の会話: {recent}
            現在の状況: {state}

            この状況で自分から話しかけるべきですか？
            話しかける場合、何と言いますか？
            """

            response = llm.generate(prompt)
            if response.should_speak:
                return response.message
        return None
```

---

## 7. 実装フェーズ

### Phase 1: 基盤整備（1-2週間）

- [ ] Memoryスキーマ拡張
- [ ] MemoryStore新メソッド実装
- [ ] deque廃止、LanceDB一本化
- [ ] スコアリング検索の実装

### Phase 2: Importance評価（1週間）

- [ ] バッチ評価の仕組み
- [ ] groq/gemini連携
- [ ] 人間フィードバック（ルールベース）

### Phase 3: Reflection（1週間）

- [ ] 閾値管理
- [ ] state=sleeping実装
- [ ] Reflectionプロンプト調整
- [ ] 汚染記憶の書き換え機能

### Phase 4: 自己発話（1週間）

- [ ] SelfTalkManager実装
- [ ] 沈黙検出
- [ ] 夢の内容を話す機能

### Phase 5: 管理画面（オプション）

- [ ] 手動Reflectionボタン
- [ ] importance手動編集
- [ ] 記憶の閲覧・書き換えUI

---

## 8. リスクと対策

| リスク | 対策 |
|--------|------|
| APIコスト増加 | バッチ処理でAPI呼び出し回数を削減 |
| Reflection中の応答停止 | state=sleepingでキャラクター化 |
| スコアリングの計算負荷 | インデックス最適化、キャッシュ活用 |
| importance評価の精度 | 人間フィードバックで補正 |

---

## 9. 成功指標

- [ ] 文脈破綻の発生頻度が減少
- [ ] コンテキスト汚染の連鎖が止まる
- [ ] ユーザーが「やめて」と言った後、同じ回答を繰り返さない
- [ ] 自己発話が自然に感じられる
- [ ] 「眠り」がキャラクターの魅力になる

---

## 10. 参考資料

- [Generative Agents (arXiv)](https://arxiv.org/abs/2304.03442)
- [LLM Powered Autonomous Agents - Lilian Weng](https://lilianweng.github.io/posts/2023-06-23-agent/)
- [Generative Agents (ACM)](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763)
