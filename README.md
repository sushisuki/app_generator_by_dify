# AI App Generator with Dify Integration

このアプリケーションは、DifyとClaude Code SDKを使用してAIが自動的にWebアプリケーションを生成・デプロイするFastAPI サーバーです。

## 機能

- ユーザーのプロンプトに基づいてAIが完全なWebアプリケーションを生成
- 生成されたアプリケーションの自動デプロイ
- 完了通知のメール送信
- バックグラウンドでの非同期処理

## 必要な環境変数

`.env`ファイルを作成し、以下の環境変数を設定してください：

```env
# SMTP設定（メール通知用）
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SENDER_EMAIL=sender@example.com

# Google Gemini API Key（AI機能を使用するアプリ生成時に必要）
GEMINI_API_KEY=your_gemini_api_key
```

## インストール

1. 必要なパッケージをインストール：
```bash
pip install fastapi uvicorn anyio python-dotenv
pip install claude-code-sdk
```

2. 環境変数ファイル（`.env`）を設定

## 使用方法

### サーバーの起動

```bash
uvicorn app:app --reload --port 8000
```

### ngrokでHTTP公開

ngrokを使用してローカルサーバーを外部からアクセス可能にできます：

1. **ngrokのインストール**：
   - https://ngrok.com/ からngrokをダウンロードしてインストール
   - アカウント作成後、認証トークンを設定

2. **サーバーの公開**：
   ```bash
   # 別のターミナルでngrokを起動
   ngrok http 8000
   ```

3. **Difyの設定**：
   - ngrokが表示するHTTPS URLをDifyのHTTP Request ツールに設定
   - 例：`https://abc123.ngrok.app/generate-code-interactive`

**注意：ngrok使用時のポイント**
- 無料版のngrokはセッション毎にURLが変わります
- 有料版では固定URLが使用可能です
- 生成されたアプリ（ポート8001）も別途公開する場合は別のngrokセッションが必要です

### APIエンドポイント

#### POST `/generate-code-interactive`

AIアプリケーション生成をリクエストします。

**リクエスト形式：**
```json
{
    "prompt": "作りたいアプリケーションの説明",
    "user_email": "notification@example.com"
}
```

**レスポンス：**
```json
{
    "response": "Task accepted. Generation of your AI-powered app is running in the background. You will receive an email upon completion."
}
```

### 処理の流れ

1. **リクエスト受付**: APIエンドポイントがリクエストを受け取り、バックグラウンドタスクを開始
2. **ワークスペース作成**: ユニークなセッションIDでワークスペースディレクトリを作成
3. **AI開発**: Claude Code SDKを使用してAIがアプリケーションコードを生成
4. **ファイル作成**: 生成されたコードを解析し、適切なファイル構造で保存
5. **自動デプロイ**: 
   - `requirements.txt`がある場合は依存関係をインストール
   - Flask アプリ（`main.py`または`app.py`）がある場合はFlask サーバーで起動
   - それ以外の場合はHTTPサーバーで静的ファイルを配信
6. **メール通知**: デプロイ完了後、アクセス可能なURLをメールで通知

### ファイル生成形式

AIは以下の形式でコードを生成する必要があります：

```
<<- FILENAME: requirements.txt ->>
Flask
python-dotenv

<<- FILENAME: main.py ->>
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello World!"

<<- FILENAME: templates/index.html ->>
<!DOCTYPE html>
<html>
<head>
    <title>Generated App</title>
</head>
<body>
    <h1>Hello from AI!</h1>
</body>
</html>
```

## 注意事項

- 生成されたアプリケーションはポート8001で実行されます
- 新しいアプリがデプロイされると、既存のアプリは停止されます
- メール設定が未設定の場合、メール通知はスキップされます
- 生成されたアプリがGoogle Gemini APIを使用する場合、親ディレクトリの`.env`ファイルから`GEMINI_API_KEY`を読み込みます

## トラブルシューティング

- **ファイル生成エラー**: AIが指定された形式でコードを生成していない場合
- **デプロイエラー**: 依存関係のインストールまたはアプリ起動に失敗した場合
- **メール送信エラー**: SMTP設定が正しくない場合

エラーの詳細はサーバーのログまたは通知メールで確認できます。
