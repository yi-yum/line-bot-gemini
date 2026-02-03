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
    
    # --- 診斷密技：輸入 "查模型" 就列出清單 ---
    if user_msg == "查模型":
        try:
            model_list = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    model_list.append(m.name)
            
            # 把清單整理成文字
            reply_text = "目前可用的模型：\n" + "\n".join(model_list)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            return # 結束，不往下跑
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"查詢失敗: {str(e)}")
            )
            return

    # --- 正常對話邏輯 ---
    try:
        # 先暫時用最保險的 'gemini-pro' (通常這是永久通用別名)
        # 等你查到正確名字後，再來改這一行
        safe_model = genai.GenerativeModel('gemini-pro') 
        
        response = safe_model.generate_content(user_msg)
        reply_text = response.text
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        error_msg = f"還是報錯: {str(e)}"
        print(error_msg)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=error_msg)
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)





