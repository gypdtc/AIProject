import os
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

def verify_results():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # 抓取所有还没验证的记录
    cur.execute("SELECT post_id, ticker, initial_price, sentiment FROM posts")
    rows = cur.fetchall()

    if not rows:
        print("数据库里还没有数据，请先成功运行 mock_test.py")
        return

    for post_id, ticker, initial_price, sentiment in rows:
        print(f"正在验证 {ticker}...")
        
        # 获取最新的瞬间价格
        stock = yf.Ticker(ticker)
        current_price = float(stock.history(period="1d")['Close'].iloc[-1])
        
        # 核心逻辑：看涨且价格涨了 = 正确
        is_correct = False
        if sentiment == 'BULLISH' and current_price >= initial_price:
            is_correct = True
        elif sentiment == 'BEARISH' and current_price <= initial_price:
            is_correct = True
            
        # 写入追踪表
        cur.execute("""
            INSERT INTO price_tracking (post_id, price_1h, is_correct_1h)
            VALUES (%s, %s, %s)
            ON CONFLICT (post_id) DO UPDATE SET is_correct_1h = EXCLUDED.is_correct_1h
        """, (post_id, current_price, is_correct))
        
        print(f"结果: 初始 ${initial_price} -> 现在 ${current_price} | AI预测: {sentiment} | 是否准确: {is_correct}")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    verify_results()
