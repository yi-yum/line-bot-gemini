import os
import sys
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import yfinance as yf

app = Flask(__name__)

# 1. 讀取環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- 【新增】全域變數：用來暫存大家的對話紀錄 ---
# 格式: { 'User_ID_123': ChatSession物件, 'User_ID_456': ChatSession物件 }
user_sessions = {}

# --- 股票小幫手函式 (保持不變) ---
def get_stock_info(symbol):
    try:
        if symbol.isdigit() and len(symbol) == 4:
            symbol = f"{symbol}.TW"
        
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        
        if data.empty:
            return None
            
        current_price = data.iloc[-1]['Close']
        info = stock.info
        name = info.get('longName', symbol)
        
        return f"【股票數據】\n代號: {symbol}\n名稱: {name}\n最新收盤價: {current_price}\n(請參考此數據回答)"
    except Exception as e:
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id # 取得發話者的 ID
    user_msg = event.message.text
    
    # 1. 檢查這個人是不是第一次來，如果是，幫他開一個新的聊天室記憶
    if user_id not in user_sessions:
        # start_chat 會開啟一個有 history 的模式
        user_sessions[user_id] = model.start_chat(history=[])
    
    # 取出這個人的專屬聊天室
    chat = user_sessions[user_id]

    # 2. 股票邏輯偵測
    stock_code = None
    match = re.search(r'\b\d{4}\b', user_msg) 
    if match:
        stock_code = match.group(0)
    
    context_data = ""
    if stock_code:
        stock_info = get_stock_info(stock_code)
        if stock_info:
            context_data = f"\n\n[系統補充資料]:\n{stock_info}"
    
    try:
        # 3. 傳送訊息給 Gemini (使用 chat.send_message 而不是 model.generate_content)
        # 這樣 Gemini 才會把這次對話寫入 history
        final_prompt = user_msg + context_data
        
        response = chat.send_message(final_prompt)
        reply_text = response.text
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        # 如果對話太長或出錯，清空記憶重來
        user_sessions[user_id] = model.start_chat(history=[])
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"記憶體重置 (錯誤: {str(e)})，請重新輸入。")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)




