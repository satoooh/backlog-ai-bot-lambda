# Backlog AI Bot (Lambda × Bedrock Claude)

Lambda単体で完結するシンプルなBacklog上の要約/QA/レビューBot。

- 受信: Backlog Webhook（コメント追加）→ Lambda Function URL（デフォルト）
- 判定: `comment.notifications[].user.id == BOT_USER_ID` で @bot 宛てメンション
- コマンド: `/summary`, `/ask <question>`, `/update`
- 出力: Backlogの該当課題にBotがコメント返信
- LLM: Amazon Bedrock Claude (Messages API)

このリポジトリは uv 管理、pytest による最小テスト、ruff による Lint/Format を備えます。

## 0. 使い方（結論）

- Backlog側: Webhookで「コメント追加」をLambda Function URLに送る（`?token=...` 付与）。
- Lambda側: 環境変数・Secretsを設定し、zipをデプロイするだけ。
- ユーザー操作: Backlog課題のコメントで `@bot /summary` 等を投稿する。

## 1. コマンド

- `@bot /summary`
- `@bot /ask <自由文の質問>`
- `@bot /update`
- 追加コンテキスト（任意）: コメント末尾に `context: <URL1> <URL2> ...`
  - 処理対象: Backlog課題URL（`/view/KEY`）とWiki URL（`/wiki/{id}`）。**HTMLスクレイプは行わず**、Backlog APIから本文/コメント/添付（メタデータ）を取得してテキスト化し、プロンプトに注入します。
  - 非BacklogのURLは無視します（セキュリティと簡素化のため）。

## 2. デプロイ（zip）

前提: AWS Lambda(Python 3.13) と Amazon Bedrock が有効化されていること。

1) zip 作成

```
uv sync --dev
uv run ruff format
uv run ruff check
uv run pytest
bash scripts/build_zip.sh
```

2) Lambda 関数作成（ハンドラ: `backlog_bot.handler.lambda_handler`）

- ランタイム: Python 3.13（本リポジトリは 3.11–3.13 で動作）
- メモリ: 256MB 以上推奨、タイムアウト: 15秒程度
- 環境変数（必須/条件付き/任意）

  必須
  - `WEBHOOK_SHARED_SECRET`（必須）: Function URL の `?token=` と照合する共有シークレット。
  - `BACKLOG_BASE_URL` または `BACKLOG_SPACE`（必須）: どちらか一方。例: `https://yourspace.backlog.com`。
  - `BACKLOG_API_KEY`（必須）: Backlog APIキー。

  条件付き必須
  - `BOT_USER_ID`（メンション必須モードで必須）: Bot（または試験的にあなた自身）の Backlog ユーザーID。

  任意（推奨・運用に応じて）
  - `IDEMPOTENCY_BUCKET`: S3バケット名。設定すると comment.id 単位で重複実行を防止（冪等化）。
  - `RECENT_COMMENT_COUNT`: 取得する直近コメント数。既定 30。
  - `CONTEXT_URL_MAX_BYTES` / `CONTEXT_TOTAL_MAX_BYTES`: context から取り込むテキスト量の上限（既定 100000 / 200000）。
  - `CONTEXT_ALLOWED_HOSTS`: 将来拡張用の許可ドメイン。現状は Backlog のみ取り込みのため未設定で可。
  - `LLM_PROVIDER`: 既定 `bedrock`。
  - `LLM_MODEL`: 既定 `anthropic.claude-3-haiku-20240307-v1:0`（用途に応じて変更）。
  - `LLM_TIMEOUT_SECONDS`: 既定 10。
  - `LLM_MAX_RETRIES`: 既定 2。
  - `REQUIRE_MENTION`: `true|false`（既定 `true`）。`false` でメンション不要の試験運用モード。
  - `ALLOWED_TRIGGER_USER_IDS`: メンション不要モード時の許可ユーザーID（CSV、例: `12345,67890`）。

- 権限（IAM）:
  - `s3:HeadObject`, `s3:PutObject`（`IDEMPOTENCY_BUCKET` を使う場合）
  - `bedrock:InvokeModel`（対象モデル）

3) エンドポイント（Function URL）

- Lambda Function URL
   - 関数に「Function URL」を有効化し、`AuthType=NONE` を選択
   - Webhook URLに `?token=YOUR_SECRET` を付与（例: `https://.../lambda-func-url?token=abc123`）
   - Lambda側は `WEBHOOK_SHARED_SECRET=abc123` を設定（本実装はヘッダ or クエリの両方をサポート）

4) Backlog Webhook

- イベント: 「課題にコメントが追加」
- URL: Lambda Function URL（`?token=...` 付き）
- 共有シークレット: 上記と一致させる

## 3. 実装の要点

- 依存は標準ライブラリ＋Lambda既定の `boto3` のみ（zipを小さく）。
- Backlog APIは `apiKey` のクエリパラメータで認証。
- Bedrock Messages API は `anthropic_version=bedrock-2023-05-31` を使用。
- LLMは最大リトライ後に失敗した場合、エラーメッセージをコメント投稿（管理者への連絡を促す）。フォールバック要約は行いません。

### メンション不要の試験運用（オプション）
- 目的: 個人アカウントでまず試せるように。理想形はbot用のアカウントを作成しておくこと
- 設定: `REQUIRE_MENTION=false` とし、`ALLOWED_TRIGGER_USER_IDS` に自分のBacklogユーザーIDを設定。
- 挙動:
  - @メンション無しでも `/summary` `/ask` `/update` を受け付けます（許可ユーザーのみ）。
  - 設定しない場合は誰でも起動できてしまうため、必ず許可ユーザーを指定してください。
  - 既存の@メンションにも対応（併用可）。

参考（APIの確認に使用）:
- Amazon Bedrock Messages API の boto3 呼び出し（`bedrock-runtime.invoke_model`）とレスポンス整形は AWS 公式ドキュメントを参照しています。
- Backlog API のエンドポイントは Backlog API v2 公式リファレンスの `GET /api/v2/issues/{issueIdOrKey}`、`GET/POST /api/v2/issues/{issueIdOrKey}/comments` を前提にしています。

## 4. ローカルテスト

```
uv sync --dev
uv run ruff format
uv run ruff check
uv run pytest
```

## 5. ハンドラ / 出力仕様

- エントリ: `backlog_bot.handler.lambda_handler`
- 処理フロー:
  1. 共有シークレット検証（`?token` または `X-Webhook-Secret`）
  2. Webhook本文から `comment` と `issue` を抽出
  3. `comment.notifications[].user.id == BOT_USER_ID` でメンション判定
  4. コマンド解析 `/summary | /ask | /update`
  5. S3で冪等化（`issueKey/commentId`）
  6. Backlogから課題/コメント取得
  7. `context:` のBacklog課題/Wiki URLをAPIで取得→テキスト化（allowlist/サイズ上限あり）
  8. Bedrock Claude呼び出し（最大リトライ）。失敗時は「管理者にお問い合わせください」旨のコメントを投稿
  9. Backlogに返信コメントを投稿

### /summary（PM志向）
- 背景/目的、現状/進捗、期限/担当、リスク/ブロッカー、次の具体アクション（1–3）
- 最後に「不足情報/確認事項」を質問として箇条書き

### /update（提案フォーマット）
- 箇条書きで「項目名: before → after （理由）」
- 項目例: 期限、優先度、状態、担当者、カスタム項目

### /ask（Q&A）
- 自然言語の質問に対して簡潔に回答（1–3段落）。
- 根拠（本文/コメント/コンテキストの短い抜粋）を示し、不確実な点や不足情報があれば明記。
- 参照範囲: 当該チケットのタイトル・説明・直近コメントN件 + `context:` で指定されたBacklog課題/Wikiの圧縮テキスト。

## 6. 制限と注意

- `context:` は Backlog の課題/Wiki URL のみ取り込み（非Backlog URL は無視）。
- 取り込みサイズは `CONTEXT_URL_MAX_BYTES` / `CONTEXT_TOTAL_MAX_BYTES` で制限。
- RAGは未対応（当該チケットと `context:` 指定の範囲のみで回答）。

---

開発規約（抜粋）: 小さく安全に、テストとドキュメント更新を同時に。依存は極力減らす、魔法は使わない、失敗はフォールバックで吸収。
