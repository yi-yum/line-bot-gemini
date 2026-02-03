import os
import sys
import re
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import yfinance as yf
from duckduckgo_search import DDGS

# --- 設定日誌 (Debug 神器) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 讀取環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY]):
    logger.error("環境變數未設定完全！請檢查 Zeabur 變數。")
    sys.exit(1)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# 記憶庫
user_sessions = {}

# --- 工具 1: 查股票 (加強防呆) ---
def get_stock_info(symbol):
    try:
        logger.info(f"正在查詢股票: {symbol}")
        if symbol.isdigit() and len(symbol) == 4:
            symbol = f"{symbol}.TW"
        
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        
        if data.empty:
            return None
            
        current_price = data.iloc[-1]['Close']
        # 嘗試取得名稱，失敗就用代號
        name = stock.info.get('longName', symbol)
        
        return f"【股價資訊】{name} ({symbol})\n現價: {current_price}"
    except Exception as e:
        logger.error(f"股票查詢失敗: {e}")
        return None

# --- 工具 2: 搜尋 (加強防呆) ---
def web_search(query):
    try:
        logger.info(f"正在搜尋網路: {query}")
        # 使用 DDGS 來搜尋
        results = DDGS().text(query, max_results=3)
        
        if not results:
            return "搜尋無結果 (可能是伺服器被擋，請稍後再試)"
            
        summary = "【網路搜尋結果】:\n"
        for i, r in enumerate(results, 1):
            title = r.get('title', '無標題')
            body = r.get('body', '無內容')
            summary += f"{i}. {title}: {body}\n"
        return summary
    except Exception as e:
        logger.error(f"網路搜尋失敗: {e}")
        return f"(網路搜尋暫時無法使用: {str(e)})"

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
    
    # 1. 記憶管理
    if user_id not in user_sessions:
        user_sessions[user_id] = model.start_chat(history=[])
    chat = user_sessions[user_id]

    # 2. 工具判斷
    tool_output = ""
    
    # [股票] 檢查是否為 4 碼數字
    stock_match = re.search(r'\b\d{4}\b', user_msg)
    if stock_match:
        stock_res = get_stock_info(stock_match.group(0))
        if stock_res:
            tool_output += stock_res + "\n"

    # [搜尋] 關鍵字觸發
    # 為了避免太敏感，我們可以設定特定的觸發詞
    search_keywords = ["搜尋", "查一下", "找一下", "新聞"]
    if any(user_msg.startswith(k) for k in search_keywords):
        # 移除關鍵字
        query = user_msg
        for k in search_keywords:
            query = query.replace(k, "", 1)
        
        search_res = web_search(query)
        if search_res:
            tool_output += "\n" + search_res

    # 3. 組合 Prompt
    final_prompt = user_msg
    system_instruction = ""
    
    if tool_output:
        system_instruction = f"\n\n[系統工具回報資料]:\n{tool_output}\n\n(請根據上述資料回答使用者的問題，如果資料不足則用你自己的知識補充)"
        final_prompt = user_msg + system_instruction

    try:
        response = chat.send_message(final_prompt)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response.text)
        )
    except Exception as e:
        logger.error(f"Gemini 回應失敗: {e}")
        # 記憶重置，避免壞掉的對話卡住
        user_sessions[user_id] = model.start_chat(history=[])
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="我剛剛恍神了，請再說一次。")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
