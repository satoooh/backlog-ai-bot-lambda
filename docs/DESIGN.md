# Backlog サマライザBot（Lambda単体）設計ドキュメント

> 小さく始めて早く回す（RAGなし）。Backlog APIとコメント本文だけで成立。

## 0. 要点

- Webhookで「課題にコメントが追加」を受信し、`comment.notifications[].user.id` に Bot のIDが含まれた場合のみ実行。
- コマンド: `@bot /summary`, `@bot /ask <質問>`, `@bot /update`
- Lambda単体で完結。リンク行 `context:` で軽量コンテキストを任意添付可。

## 1. 監視とセキュリティ

- Backlog管理画面 → Webhook → イベント: コメント追加。
- Lambda Function URL + `?token=` で受信（`WEBHOOK_SHARED_SECRET` と照合）。
- 冪等性: `S3` に `issueKey/commentId` を保存し、重複実行を抑止。

## 2. コマンド仕様

- `@bot /summary`
- `@bot /ask <自由文の質問>`
- `@bot /update`（期限/優先度/状態/担当の整合レビューと提案）
- 追加: コメント末尾 `context: <URL1> <URL2> ...`
  - Backlog課題URL（/view/PROJ-123）をAPIで取得してテキスト化（HTMLスクレイプは行わない）。
  - 非BacklogURLは無視。

## 3. アーキテクチャ（Lambda単体）

```
Backlog Webhook (comment_added)
  -> Lambda Function URL (AuthType=NONE, ?token=...)
      -> Lambda handler
          - verify secret (?token or X-Webhook-Secret)
          - idempotency (S3)
          - parse command
          - fetch issue + recent comments (Backlog API)
          - fetch link-context (Backlog issue/wiki via API)
          - prompt build + Bedrock Claude
          - render markdown reply
          - post comment (Backlog API)
```

### 環境変数（抜粋）

- `BACKLOG_SPACE`, `BACKLOG_BASE_URL`
- `BOT_USER_ID`
- `WEBHOOK_SHARED_SECRET`
- `BACKLOG_API_KEY`
- `IDEMPOTENCY_BUCKET`
- `RECENT_COMMENT_COUNT`
- `CONTEXT_URL_MAX_BYTES`, `CONTEXT_TOTAL_MAX_BYTES`, `CONTEXT_ALLOWED_HOSTS`
- `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`

### 主要API

- `GET /api/v2/issues/{issueIdOrKey}`
- `GET /api/v2/issues/{issueIdOrKey}/comments?count=N`
- `POST /api/v2/issues/{issueIdOrKey}/comments`

## 4. 失敗時の動作

- LLM失敗: `LLM_MAX_RETRIES` 回まで再試行し、それでも失敗した場合は「管理者にお問い合わせください」旨をBacklogにコメント投稿する。
- 投稿失敗: Lambdaエラー（必要に応じてDLQを設定）。

## 5. 出力仕様

- /summary: PM志向（背景/目的、現状/進捗、期限/担当、リスク/ブロッカー、次アクション1–3、最後に不足情報の質問）
- /update: 箇条書き「項目名: before → after （理由）」で更新提案
- /ask: 自然言語Q&A。回答は簡潔（1–3段落）。根拠（本文/コメント/コンテキストの短い抜粋）を示し、不確実な点や不足情報があれば明記する。

## 6. 将来拡張

- `@bot apply ...` で人手承認→自動反映。
- `context:` にBacklog課題キー列挙を許可して関連チケットを追加参照。
- RAG: S3 キャッシュ＋上位Kのみインジェスト。
