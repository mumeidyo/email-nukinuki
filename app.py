import os
import requests
from flask import Flask, redirect, request, url_for, session, render_template_string

app = Flask(__name__)
# 本番環境ではより複雑なシークレットキーを環境変数で設定することを推奨
# 例: app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24)) 

# 環境変数からDiscord APIの情報を取得
# Renderにデプロイする際、これらの環境変数を設定してください
CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
# REDIRECT_URIはRenderのURLに "/callback" を付けたものになります
# 例: https://your-service-name.onrender.com/callback
REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI") 

DISCORD_API_BASE_URL = "https://discord.com/api/v10"

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
    </style>
</head>
<body>
    <h1>Discord メールアドレス取得デモ</h1>
    {% if user_email %}
        <p class="message">こんにちは、**{{ user_email }}** さん！</p>
        <p><a href="/logout" class="button">ログアウト</a></p>
    {% else %}
        <p class="message">Discordアカウントでログインしてメールアドレスを取得します。</p>
        <p><a href="/login" class="button">Discordでログイン</a></p>
    {% endif %}
</body>
</html>
"""

# --- Flask ルート定義 ---

@app.route('/')
def index():
    """
    トップページを表示。ログイン状態によって表示内容が変わる。
    """
    # セッションからメールアドレスを取得
    user_email = session.get('user_email')
    return render_template_string(INDEX_HTML, user_email=user_email)

@app.route('/login')
def login():
    """
    ユーザーをDiscordのOAuth2認証ページにリダイレクト。
    """
    if not (CLIENT_ID and REDIRECT_URI):
        return "Error: Discord CLIENT_ID or REDIRECT_URI is not set. Please check environment variables.", 500

    # identify と email スコープを要求
    oauth_url = (
        f"{DISCORD_API_BASE_URL}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=identify%20email" # ここで identify と email スコープを指定
    )
    return redirect(oauth_url)

@app.route('/callback')
def callback():
    """
    Discordからの認証コールバックを受け取り、アクセストークンとユーザー情報を取得。
    """
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        # ユーザーが認証を拒否した場合など
        return f"認証が拒否されました。エラー: {error}. <a href='/'>戻る</a>", 400

    if not code:
        return "認証エラー: 認証コードがありません。<a href='/'>戻る</a>", 400

    if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
        return "Error: Discord environment variables are not set. Please check environment variables.", 500

    # 認証コードをアクセストークンに交換
    token_url = f"{DISCORD_API_BASE_URL}/oauth2/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify email' # ここも一致させる
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(token_url, data=data, headers=headers)
        response.raise_for_status() # HTTPエラーが発生した場合に例外を投げる
        token_info = response.json()
    except requests.exceptions.RequestException as e:
        print(f"アクセストークン取得エラー: {e}")
        return f"アクセストークンの取得に失敗しました: {e}. <a href='/'>戻る</a>", 500

    access_token = token_info.get('access_token')
    if not access_token:
        print(f"アクセストークンがレスポンスに含まれていません: {token_info}")
        return "アクセストークンの取得に失敗しました。<a href='/'>戻る</a>", 500

    # アクセストークンを使ってユーザー情報を取得
    user_info_url = f"{DISCORD_API_BASE_URL}/users/@me"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status() # HTTPエラーが発生した場合に例外を投げる
        user_data = user_response.json()
    except requests.exceptions.RequestException as e:
        print(f"ユーザー情報取得エラー: {e}")
        return f"ユーザー情報の取得に失敗しました: {e}. <a href='/'>戻る</a>", 500

    # メールアドレスが存在し、Noneでないかを確認
    user_email = user_data.get('email')
    
    if user_email:
        session['user_email'] = user_email # セッションにメールアドレスを保存
        # ここでデータベースなどにメールアドレスとユーザーIDを保存する処理を行う
        # 例: save_email_to_database(user_data['id'], user_email)
        print(f"ユーザーID: {user_data.get('id')}, メールアドレス: {user_email} を取得しました。")
        return redirect(url_for('index')) # トップページに戻る
    else:
        # メールアドレスが取得できない場合（ユーザーがメールを検証していない、
        # またはスコープを許可しなかった、など）
        # この場合でも、ユーザーID (user_data.get('id')) は identify スコープで取得できます
        print(f"ユーザーID: {user_data.get('id')} は取得しましたが、メールアドレスは利用できませんでした。")
        session['user_email'] = "メールアドレスなし（または未検証）" # 表示用に設定
        return redirect(url_for('index')) # トップページに戻る

@app.route('/logout')
def logout():
    """
    ユーザーをログアウトさせ、セッションをクリアする。
    """
    session.pop('user_email', None) # セッションからメールアドレスを削除
    return redirect(url_for('index')) # トップページに戻る

if __name__ == '__main__':
    # RenderはGunicornのようなWSGIサーバーを使ってアプリケーションを起動します。
    # この 'if __name__ == "__main__":' ブロックは、ローカル開発環境でのみ実行されます。
    # RenderはProcfileに従ってGunicornを起動するため、この部分は無視されます。
    print("ローカル開発サーバーを起動中...")
    print(f"Discord CLIENT_ID: {CLIENT_ID}")
    print(f"Discord REDIRECT_URI: {REDIRECT_URI}")
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
