import os
import time
import json
import psycopg2
import google.generativeai as genai
import yfinance as yf
from dotenv import load_dotenv

# 1. 加载配置
load_dotenv()

# 配置 AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 使用你之前测试成功的模型名称
MODEL_NAME = 'gemini-2.5-flash' 

def get_sentiment_safe(text):
    """调用 AI 分析情绪，并安全解析 JSON"""
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = (
        f"Analyze the stock ticker and sentiment (BULLISH/BEARISH/NEUTRAL) from this text. "
        f"Reply ONLY in raw JSON format like {{\"ticker\": \"AAPL\", \"sentiment\": \"BULLISH\"}}. "
        f"Text: {text}"
    )
    
    try:
        response = model.generate_content(prompt)
        # 清洗可能存在的 Markdown 标签 (```json ... ```)
        clean_content = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean_content)
    except Exception as e:
        print(f"AI 解析出错: {e}")
        return None

def run_mock_process():
    # 模拟从 Reddit 抓取到的数据
    mock_reddit_posts = [
        {"id": "m_001", "title": "NVDA looks unstoppable after the AI summit!", "body": "I am buying more calls tomorrow."},
        {"id": "m_002", "title": "TSLA delivery numbers are disappointing.", "body": "Expecting a huge drop next week, staying bearish."},
        {"id": "m_003", "title": "Is it time to buy the dip on AAPL?", "body": "The stock has been sideways for months, maybe neutral for now."}
    ]

    # 建立数据库连接
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        print("Successfully connected to PostgreSQL.")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return

    for post in mock_reddit_posts:
        print(f"\n--- 正在处理帖子 ID: {post['id']} ---")
        
        # A. 获取 AI 分析结果
        analysis = get_sentiment_safe(post['title'] + " " + post['body'])
        
        if analysis and analysis.get('ticker') != 'UNKNOWN':
            ticker = analysis['ticker'].strip('$').upper()
            sentiment = analysis['sentiment'].upper()
            
            print(f"AI 识别结果: {ticker} | 情绪: {sentiment}")

            # B. 获取当前市场价格 (yfinance)
            try:
                stock_data = yf.Ticker(ticker)
                # 获取最新的收盘价
                initial_price = float(stock_data.history(period="1d")['Close'].iloc[-1])
            except Exception as e:
                print(f"获取 {ticker} 价格失败: {e}")
                initial_price = 0

            # C. 存入数据库
            if initial_price > 0:
                try:
                    cur.execute("""
                        INSERT INTO posts (post_id, title, ticker, initial_price, sentiment)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (post_id) DO NOTHING
                    """, (post['id'], post['title'], ticker, initial_price, sentiment))
                    print(f"数据已入库: {ticker} 初始价 ${initial_price:.2f}")
                except Exception as e:
                    print(f"数据库写入报错: {e}")
            
        # D. 频率限制：为了避开免费层的 429 错误，每个循环休息 10 秒
        print("等待 10 秒以避开 API 频率限制...")
        time.sleep(10)

    # 提交事务并关闭
    conn.commit()
    cur.close()
    conn.close()
    print("\n--- 所有模拟数据处理完毕！ ---")

if __name__ == "__main__":
    run_mock_process()
