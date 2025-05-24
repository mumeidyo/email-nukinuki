import os
import requests
import threading
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
from flask import Flask, redirect, request, url_for, session, render_template_string, jsonify

app = Flask(__name__)
# Flaskセッションを安全に保つためのシークレットキー
# 本番環境ではより複雑な文字列を環境変数で設定することを強く推奨
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24)) 

# --- Discord OAuth2 Web Service の設定 ---
CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
# RenderにデプロイされたFlaskアプリのコールバックURL
# 例: https://email-nukinuki.onrender.com/callback
REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI") 

DISCORD_API_BASE_URL = "https://discord.com/api/v10"

# --- Discord Bot の設定 ---
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読み取る権限 (コマンド処理に必要)
intents.members = True          # サーバーのメンバー情報を取得する権限 (Botがオンライン状態を示すためにも有効)

bot = commands.Bot(command_prefix='!', intents=intents)

# Botトークン
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# Botのオンライン状態を管理する変数
bot_online_status = "オフライン"

@bot.event
async def on_ready():
    """BotがDiscordにログインして準備ができたときに呼び出されます。"""
    global bot_online_status
    bot_online_status = "オンライン"
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    # Botのステータスを設定（例: プレイ中「認証待機中」）
    await bot.change_presence(activity=discord.Game(name="認証待機中"))


@bot.event
async def on_disconnect():
    """BotがDiscordから切断されたときに呼び出されます。"""
    global bot_online_status
    bot_online_status = "切断されました"
    print(f'Bot disconnected.')

@bot.event
async def on_resumed():
    """Botが再接続されたときに呼び出されます。"""
    global bot_online_status
    bot_online_status = "オンライン"
    print(f'Bot reconnected.')

@bot.command(name='addbutton')
async def add_authentication_button(ctx):
    """
    '!addbutton' コマンドで認証ボタンを送信します。
    OAUTH_WEB_URL は、RenderにデプロイされたFlaskアプリのトップページのURL
    """
    # この例では OAUTH_WEB_URL をコードに直接記述していますが、
    # 環境変数から取得するように変更することも可能です。
    # OAUTH_WEB_URL = os.environ.get("OAUTH_WEB_URL", "https://email-nukinuki.onrender.com/")
    OAUTH_WEB_URL_FOR_BUTTON = "https://email-nukinuki.onrender.com/" # BotのボタンからリンクするURL

    if not OAUTH_WEB_URL_FOR_BUTTON:
        await ctx.send("エラー: 認証用WebサービスのURLが設定されていません。")
        return

    auth_button = Button(label="認証する", style=discord.ButtonStyle.link, url=OAUTH_WEB_URL_FOR_BUTTON)
    view = View()
    view.add_item(auth_button)

    await ctx.send("インタラクションボタンで認証\n認証してください", view=view)

# --- Flask ルート定義 ---

# Botの状態をフロントエンドに伝えるためのAPIエンドポイント
@app.route('/bot_status')
def get_bot_status():
    """
    Botの現在のオンライン状態をJSONで返すAPIエンドポイント。
    """
    return jsonify(status=bot_online_status)

# --- HTMLテンプレート（シンプルにするためコード内に直接記述） ---
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord メールアドレス取得</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .button {
            display: inline-block;
            padding: 10px 20px;
            font-size: 1.2em;
            color: white;
            background-color: #7289DA;
            border: none;
            border-radius: 5px;
            text-decoration: none;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        .button:hover {
            background-color: #677BC4;
        }
        .message {
            margin-top: 20px;
            font-size: 1.1em;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 5px;
            font-weight: bold;
            color: white;
            background-color: gray;
        }
        .status-online { background-color: green; }
        .status-offline { background-color: red; }
        .status-disconnected { background-color: orange; }
    </style>
</head>
<body>
    <h1>Discord メールアドレス取得デモ</h1>
    <p class="message">Discord Botの状態: <span id="bot-status" class="status-badge">ロード中...</span></p>
    {% if user_email %}
        <p class="message">こんにちは、**{{ user_email }}** さん！</p>
        <p><a href="/logout" class="button">ログアウト</a></p>
    {% else %}
        <p class="message">Discordアカウントでログインしてメールアドレスを取得します。</p>
        <p><a href="/login" class="button">Discordでログイン</a></p>
    {% endif %}

    <script>
        // Botの状態を動的に更新する（フロントエンドからの表示のみ）
        document.addEventListener('DOMContentLoaded', function() {
            function updateBotStatus() {
                fetch('/bot_status')
                    .then(response => response.json())
                    .then(data => {
                        const statusElement = document.getElementById('bot-status');
                        statusElement.textContent = data.status;
                        statusElement.className = 'status-badge'; // Reset classes
                        if (data.status === 'オンライン') {
                            statusElement.classList.add('status-online');
                        } else if (data.status === 'オフライン') {
                            statusElement.classList.add('status-offline');
                        } else if (data.status === '切断されました') {
                            statusElement.classList.add('status-disconnected');
                        }
                    })
                    .catch(error => {
                        console.error('Bot status fetch error:', error);
                        const statusElement = document.getElementById('bot-status');
                        statusElement.textContent = '取得失敗';
                        statusElement.classList.add('status-offline');
                    });
            }
            // ページロード時に更新
            updateBotStatus();
            // 5秒ごとに更新（Botが落ちた場合に検知するため）
            setInterval(updateBotStatus, 5000); 
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    user_email = session.get('user_email')
    return render_template_string(INDEX_HTML, user_email=user_email)

@app.route('/login')
def login():
    if not (CLIENT_ID and REDIRECT_URI):
        return "Error: Discord CLIENT_ID or REDIRECT_URI is not set. Please check environment variables.", 500

    oauth_url = (
        f"{DISCORD_API_BASE_URL}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=identify%20email"
    )
    return redirect(oauth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        return f"認証が拒否されました。エラー: {error}. <a href='/'>戻る</a>", 400
    if not code:
        return "認証エラー: 認証コードがありません。<a href='/'>戻る</a>", 400
    if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
        return "Error: Discord environment variables are not set. Please check environment variables.", 500

    token_url = f"{DISCORD_API_BASE_URL}/oauth2/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify email'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(token_url, data=data, headers=headers)
        response.raise_for_status()
        token_info = response.json()
    except requests.exceptions.RequestException as e:
        print(f"アクセストークン取得エラー: {e}")
        return f"アクセストークンの取得に失敗しました: {e}. <a href='/'>戻る</a>", 500

    access_token = token_info.get('access_token')
    if not access_token:
        print(f"アクセストークンがレスポンスに含まれていません: {token_info}")
        return "アクセストークンの取得に失敗しました。<a href='/'>戻る</a>", 500

    user_info_url = f"{DISCORD_API_BASE_URL}/users/@me"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
    except requests.exceptions.RequestException as e:
        print(f"ユーザー情報取得エラー: {e}")
        return f"ユーザー情報の取得に失敗しました: {e}. <a href='/'>戻る</a>", 500

    user_email = user_data.get('email')
    
    if user_email:
        session['user_email'] = user_email
        print(f"ユーザーID: {user_data.get('id')}, メールアドレス: {user_email} を取得しました。")
        return redirect(url_for('index'))
    else:
        print(f"ユーザーID: {user_data.get('id')} は取得しましたが、メールアドレスは利用できませんでした。")
        session['user_email'] = "メールアドレスなし（または未検証）"
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('index'))

# --- Botの起動を別スレッドで行う関数 ---
def run_discord_bot():
    """
    Discord Botを非同期イベントループ内で実行する。
    """
    if BOT_TOKEN:
        try:
            # asyncio イベントループを新しいスレッドで実行
            asyncio.run(bot.start(BOT_TOKEN))
        except discord.LoginFailure:
            print("Botトークンが無効です。Botを起動できませんでした。")
        except Exception as e:
            print(f"Botの実行中に予期せぬエラーが発生しました: {e}")
            global bot_online_status
            bot_online_status = "エラー"
    else:
        print("エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。Botを起動できません。")

# --- アプリケーションの起動 ---
if __name__ == '__main__':
    # Flaskアプリの起動前にBotを別スレッドで起動する
    # これはローカル開発環境でのみ機能します。
    # RenderはProcfileでgunicornを起動するため、このブロックはRenderでは直接実行されません。
    print("ローカル開発サーバーとBotを起動中...")
    print(f"Discord CLIENT_ID: {CLIENT_ID}")
    print(f"Discord REDIRECT_URI: {REDIRECT_URI}")
    
    # Botのスレッドをデーモンとして開始（メインスレッドが終了したら自動終了）
    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()

    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
