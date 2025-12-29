import os
import praw
import psycopg2
import google.generativeai as genai
from datetime import datetime

# 1. 配置环境（从云端环境变量读取）
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# 如果你使用了 Reddit API，请在 GitHub Secrets 添加这些值
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

def get_reddit_trends():
    """从 Reddit 抓取热门讨论"""
    print("正在连接 Reddit...")
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent="StockScanner v1.0"
    )
    # 监控 wallstreetbets 频道
    posts = reddit.subreddit("wallstreetbets").hot(limit=10)
    data = []
    for post in posts:
        data.append(f"Title: {post.title}\nContent: {post.selftext[:200]}")
    return "\n---\n".join(data)

def analyze_with_gemini(text):
    """使用 Gemini AI 分析股票倾向"""
    print("正在调用 Gemini AI 分析内容...")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    从以下文本中提取提到的股票代码（Ticker）和市场情绪（Bullish/Bearish/Neutral）。
    请仅以以下格式返回：TICKER:SENTIMENT
    例如：AAPL:Bullish, TSLA:Bearish
    文本内容：{text}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def save_to_db(results):
    """将结果存入 Neon 数据库"""
    print(f"正在保存结果到数据库: {results}")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 确保表存在
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_trends (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10),
            sentiment VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 解析并插入数据
    pairs = results.split(",")
    for pair in pairs:
        if ":" in pair:
            ticker, sentiment = pair.split(":")
            cur.execute(
                "INSERT INTO stock_trends (ticker, sentiment) VALUES (%s, %s)",
                (ticker.strip(), sentiment.strip())
            )
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ 任务完成！数据已同步到云端数据库。")

if __name__ == "__main__":
    try:
        raw_text = get_reddit_trends()
        analysis = analyze_with_gemini(raw_text)
        save_to_db(analysis)
    except Exception as e:
        print(f"❌ 运行出错: {e}")