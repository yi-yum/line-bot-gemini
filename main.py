import os
import sys
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# 1. 讀取環境變數 (在 Zeabur 設定)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 2. 初始化 Line Bot 與 Gemini
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

genai.configure(api_key=GEMINI_API_KEY)
# 使用最快的 Flash 模型
model = genai.GenerativeModel('gemini-1.5-flash')

# 3. 監聽 Line 的訊息 (Webhook)
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 4. 當收到文字訊息時
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    try:
        # 讓 Gemini 思考回應
        response = model.generate_content(user_msg)
        reply_text = response.text
        
        # 回傳給 Line
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        # 如果出錯 (例如 Gemini 擋掉敏感詞)，回報錯誤
        error_msg = f"發生錯誤: {str(e)}"
        print(error_msg)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="抱歉，我現在有點錯亂，請再試一次。")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
