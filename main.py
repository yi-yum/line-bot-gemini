import os
import sys
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import yfinance as yf
from duckduckgo_search import DDGS

app = Flask(__name__)

# 1. 環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

genai.configure(api_key=GEMINI_API_KEY)
# 使用 2.5 Flash 模型
model = genai.GenerativeModel('gemini-2.5-flash')

# 記憶庫
user_sessions = {}

# --- 工具 1: 查股票 ---
def get_stock_info(symbol):
    try:
        if symbol.isdigit() and len(symbol) == 4:
            symbol = f"{symbol}.TW"
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        if data.empty: return None
        price = data.iloc[-1]['Close']
        name = stock.info.get('longName', symbol)
        return f"【股票快搜】{name} ({symbol}) 收盤價: {price}"
    except: return None

# --- 工具 2: 聯網搜尋 (DuckDuckGo) ---
def web_search(query):
    try:
        results = DDGS().text(query, max_results=3)
        if not results: return None
        summary = "【網路搜尋結果】:\n"
        for i, r in enumerate(results, 1):
            summary += f"{i}. {r['title']}: {r['body']}\n"
        return summary
    except Exception as e:
        return f"搜尋失敗: {str(e)}"

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
    user_id = event.source.user_id
    user_msg = event.message.text.strip()
    
    # 初始化記憶
    if user_id not in user_sessions:
        user_sessions[user_id] = model.start_chat(history=[])
    chat = user_sessions[user_id]

    # --- 智慧判斷邏輯 (簡易版 Agent) ---
    tool_output = ""
    
    # 1. 判斷是否查股票 (4碼數字)
    stock_match = re.search(r'\b\d{4}\b', user_msg)
    if stock_match:
        stock_info = get_stock_info(stock_match.group(0))
        if stock_info:
            tool_output += stock_info + "\n"

    # 2. 判斷是否需要上網搜尋 (關鍵字觸發)
    # 這裡我們用簡單的關鍵字，如果要更聰明可以讓 Gemini 決定
    search_keywords = ["搜尋", "查一下", "新聞", "最新的", "是誰", "什麼是"]
    if any(k in user_msg for k in search_keywords):
        # 移除關鍵字後再去搜，效果比較好
        query = user_msg
        for k in search_keywords:
            query = query.replace(k, "")
        
        search_res = web_search(query)
        if search_res:
            tool_output += "\n" + search_res

    # 3. 組合 Prompt
    # 如果有工具產生的資料，就加在前面餵給 Gemini
    final_prompt = user_msg
    if tool_output:
        final_prompt = f"{tool_output}\n\n使用者問題: {user_msg}\n(請根據上方資料回答，如果是股票請分析，如果是搜尋結果請總結)"

    try:
        response = chat.send_message(final_prompt)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.text))
    except Exception as e:
        # 記憶重置防呆
        user_sessions[user_id] = model.start_chat(history=[])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="我剛剛恍神了，請再說一次。"))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)



