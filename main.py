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
# 使用剛剛查到的最強模型
model = genai.GenerativeModel('gemini-2.5-flash')

# --- 股票小幫手函式 ---
def get_stock_info(symbol):
    try:
        # 判斷是否為台股 (如果是 4 位數字，預設加上 .TW)
        if symbol.isdigit() and len(symbol) == 4:
            symbol = f"{symbol}.TW"
        
        stock = yf.Ticker(symbol)
        # 取得即時資料
        data = stock.history(period="1d")
        
        if data.empty:
            return None
            
        current_price = data.iloc[-1]['Close']
        # 嘗試取得基本面資訊 (如果有的話)
        info = stock.info
        name = info.get('longName', symbol)
        
        return f"【股票數據】\n代號: {symbol}\n名稱: {name}\n最新收盤價: {current_price}\n(請根據以上數據進行分析)"
    except Exception as e:
        return None

# 2. 監聽 Line 的訊息
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 3. 處理訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    
    # --- 股票觸發邏輯 ---
    # 檢查訊息裡面有沒有 4 位數字 (例如 2330)
    stock_code = None
    match = re.search(r'\b\d{4}\b', user_msg) 
    if match:
        stock_code = match.group(0)
    
    context_data = ""
    if stock_code:
        # 如果有股票代碼，先去抓資料
        stock_info = get_stock_info(stock_code)
        if stock_info:
            context_data = f"\n\n[系統提供的即時資料]:\n{stock_info}"
    
    try:
        # 把「使用者問題」+「抓到的股價」一起丟給 Gemini
        final_prompt = user_msg + context_data
        
        response = model.generate_content(final_prompt)
        reply_text = response.text
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"分析失敗: {str(e)}")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)




