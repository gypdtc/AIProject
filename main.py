import os
import praw
import google.generativeai as genai
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

def get_sentiment_via_gemini(text):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Analyze the following stock market post. Identify the stock ticker and sentiment. Reply ONLY in JSON format: {{\"ticker\": \"TICKER\", \"sentiment\": \"BULLISH/BEARISH/NEUTRAL\"}}. Text: {text[:500]}"
    
    try:
        response = model.generate_content(prompt)
        # 简单的字符串清洗，防止 AI 返回 Markdown 代码块
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return eval(clean_json) # 实际生产建议使用 json.loads
    except:
        return None

def run_scraper():
    # 连接数据库
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # 初始化 Reddit
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_SECRET"),
        user_agent="windows:stock-scanner:v1.0"
    )

    print("正在扫描 r/stocks...")
    for post in reddit.subreddit("stocks").hot(limit=5):
        analysis = get_sentiment_via_gemini(post.title + post.selftext)
        
        if analysis and analysis['ticker'] != 'TICKER':
            ticker = analysis['ticker'].strip('$')
            sentiment = analysis['sentiment']
            
            # 获取当前股价
            stock = yf.Ticker(ticker)
            current_price = stock.history(period="1d")['Close'].iloc[-1]

            # 存入数据库
            cur.execute("""
                INSERT INTO posts (post_id, title, ticker, initial_price, sentiment)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
            """, (post.id, post.title, ticker, current_price, sentiment))
            
            print(f"已记录: {ticker} | 情绪: {sentiment} | 价格: {current_price}")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_scraper()
