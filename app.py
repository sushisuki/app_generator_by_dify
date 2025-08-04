import anyio
import os
import smtplib
import subprocess
import time
import uuid
import re
from email.mime.text import MIMEText
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# claude-code-sdkから必要なコンポーネントをインポート
from claude_code_sdk import (
    query, 
    ClaudeCodeOptions, 
    AssistantMessage, 
    TextBlock
)

# --- メール設定 (環境変数から読み込み) ---
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

# FastAPIアプリケーションを初期化
app = FastAPI()

# --- バックグラウンドで実行される関数 ---
def send_completion_email(recipient_email: str, subject: str, body: str):
    """メールを送信する関数"""
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        print("Email environment variables are not set. Skipping email notification.")
        return

    msg = MIMEText(body, 'html') # HTML形式でメールを送信
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [recipient_email], msg.as_string())
        print(f"Completion email sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def parse_and_create_files(app_dir: Path, full_code_string: str):
    """AIが生成した単一のテキストから、複数のファイルをパースして作成する"""
    print("--- Starting File Parsing and Creation ---")
    # 正規表現でファイルパスとコード内容を抽出
    # 例: <<- FILENAME: templates/index.html ->>
    file_pattern = re.compile(r"<<- FILENAME: (.+?) ->>\n(.*?)(?=\n<<- FILENAME:|\Z)", re.DOTALL)
    
    files_created = 0
    for match in file_pattern.finditer(full_code_string):
        relative_path = match.group(1).strip()
        content = match.group(2).strip()
        
        file_path = app_dir / relative_path
        
        # サブディレクトリが存在しない場合は作成
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # ファイルに書き込み
        file_path.write_text(content, encoding='utf-8')
        print(f"Created file: {file_path}")
        files_created += 1
        
    if files_created == 0:
        raise ValueError("AI did not generate code in the expected format. No files were created.")
    print(f"--- Finished File Parsing and Creation. {files_created} files created. ---")

def find_deployable_app(base_dir: Path) -> Path | None:
    """指定されたディレクトリ内を再帰的に検索し、デプロイ可能なアプリのルートディレクトリを探す"""
    # まず 'main.py' または 'app.py' を探す
    for main_file in list(base_dir.glob("**/main.py")) + list(base_dir.glob("**/app.py")):
        return main_file.parent
    
    # Flaskアプリが見つからなければ 'index.html' を探す
    for index_file in base_dir.glob("**/index.html"):
        return index_file.parent
        
    return None


async def run_code_generation_task(prompt: str, user_email: str):
    """
    リクエストごとにユニークなディレクトリを生成し、単一の強力なAIエージェントがアプリを開発・デプロイし、URLをメールで送信する。
    """
    session_id = uuid.uuid4().hex[:8]
    app_dir_name = f"workspace_{session_id}"
    app_dir = Path.cwd() / app_dir_name
    
    print(f"Starting single-agent background task in '{app_dir_name}' for user: {user_email}")
    
    try:
        # --- 最初にPythonで安全に作業ディレクトリを作成 ---
        app_dir.mkdir(parents=True, exist_ok=True)
        print(f"Workspace directory created at: {app_dir}")

        # --- 単一のフルスタック開発エージェントによる開発 ---
        generation_prompt = f"""
You are an expert, autonomous full-stack software development agent. Your goal is to build a complete, working web application based on the user's request: '{prompt}'.

**Your Task:**
Generate the complete code for all necessary files as a single text block.
You **MUST** format your output by clearly separating each file's content with a special marker.

**Output Format Rules:**
- Each file must start with a marker: `<<- FILENAME: path/to/your/file.ext ->>`
- The file path should be relative (e.g., `main.py` or `templates/index.html`).
- The code for that file must immediately follow the marker.
- Do not add any other text or explanations outside of the code blocks.

**Example Output:**
<<- FILENAME: requirements.txt ->>
Flask
python-dotenv
google-generativeai

<<- FILENAME: main.py ->>
from flask import Flask
# ... rest of the python code ...

<<- FILENAME: templates/index.html ->>
<!DOCTYPE html>
<html>
<!-- ... rest of the html code ... -->
</html>

**Development Plan:**
1.  **Analyze and Plan:**
    - Carefully analyze the user's request: '{prompt}'.
    - Determine the necessary files and directory structure.
    - If the request requires AI features, plan to use the Google Gemini API.
2.  **Generate Code:**
    - Write the full code for all files according to the output format rules above.
    - If using an API key, the generated Python code **MUST** load the `GEMINI_API_KEY` from a `.env` file located in the PARENT directory (`../.env`).
"""
        generation_options = ClaudeCodeOptions(
            max_turns=5, # テキストを一度に生成するため、ターン数は少なくて良い
        )
        print(f"--- Starting Development Phase for {app_dir_name} ---")
        
        full_generated_text = ""
        async for message in query(prompt=generation_prompt, options=generation_options):
            print(f"Development phase ({app_dir_name}) received message type: {type(message).__name__}")
            if isinstance(message, AssistantMessage) and isinstance(message.content[0], TextBlock):
                full_generated_text += message.content[0].text
        
        print(f"--- Development Phase Finished for {app_dir_name} ---")

        # --- Pythonコードでファイルをパースして作成 ---
        parse_and_create_files(app_dir, full_generated_text)

        # --- フェーズ2: デプロイと通知 ---
        print(f"Attempting to deploy locally from {app_dir_name}.")
        deploy_port = 8001
        
        # --- 生成されたアプリのルートディレクトリを賢く探す ---
        deploy_dir = find_deployable_app(app_dir)
        if deploy_dir is None:
             raise FileNotFoundError("AI agent failed to generate a deployable 'main.py' or 'index.html' file anywhere in the workspace.")

        print(f"Found deployable application at: {deploy_dir}")

        try:
            kill_command = ["fuser", "-k", f"{deploy_port}/tcp"]
            subprocess.run(kill_command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Attempted to kill any existing process on port {deploy_port}.")
            time.sleep(1)
        except FileNotFoundError:
            print("'fuser' command not found. Skipping process kill.")
        
        app_dir_path = str(deploy_dir)
        try:
            if (deploy_dir / "requirements.txt").is_file():
                pip_command = ["python", "-m", "pip", "install", "-r", "requirements.txt"]
                subprocess.run(pip_command, cwd=app_dir_path, check=True, capture_output=True, text=True)
                print("Dependencies for generated app installed successfully.")

            main_py_file = "main.py" if (deploy_dir / "main.py").is_file() else "app.py"
            if (deploy_dir / main_py_file).is_file():
                env = os.environ.copy()
                env["FLASK_APP"] = main_py_file
                run_command = ["python", "-m", "flask", "run", "--port", str(deploy_port)]
                subprocess.Popen(run_command, cwd=app_dir_path, env=env)
            else:
                 run_command = ["python", "-m", "http.server", str(deploy_port)]
                 subprocess.Popen(run_command, cwd=app_dir_path)

        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies for the generated app: {e.stderr}")
            raise e
        except Exception as deploy_e:
            print(f"Failed to deploy the generated app: {deploy_e}")
            raise deploy_e
        
        app_url = f"http://localhost:{deploy_port}"
        print(f"Application from {app_dir_name} deployed locally at: {app_url}")

        subject = "Your AI-Powered App Has Been Generated and Deployed!"
        body = f"""
        <p>Your request to generate an application for '<b>{prompt}</b>' has been completed.</p>
        <p>The generated application has been deployed locally. You can access it here:</p>
        <p><a href="{app_url}">{app_url}</a></p>
        <p><b>Important:</b> This URL is shared. If another build is run, this URL will point to the new application.</p>
        <hr>
        <p>This application was autonomously generated by an AI agent.</p>
        <hr>
        <p>Note: This server is running on the machine where the API is hosted. It will stop if the main application is terminated.</p>
        """
        send_completion_email(user_email, subject, body)

    except Exception as e:
        print(f"An error occurred in background task for {app_dir_name}: {e}")
        subject = "Code Generation Failed"
        body = f"<p>An error occurred while processing your request for '{prompt}'.</p><p><b>Error:</b> {e}</p>"
        send_completion_email(user_email, subject, body)


# --- APIエンドポイント ---
class CodeRequest(BaseModel):
    prompt: str
    user_email: str

@app.post("/generate-code-interactive")
async def generate_code_interactive(request: CodeRequest, background_tasks: BackgroundTasks):
    """
    Difyからのリクエストを受け付け、重い処理をバックグラウンドタスクとして登録し、
    すぐに「受け付けました」というレスポンスを返す。
    """
    if not request.user_email:
        return {"error": "user_email is required for notification."}

    background_tasks.add_task(run_code_generation_task, request.prompt, request.user_email)
    
    return {"response": "Task accepted. Generation of your AI-powered app is running in the background. You will receive an email upon completion."}

# サーバーを起動するには、ターミナルで以下のコマンドを実行します:
# uvicorn app:app --reload --port 8000
