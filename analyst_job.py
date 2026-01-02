import os
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

def get_price_change(ticker, start_time):
    """获取股票在特定时间点的价格变化"""
    try:
        stock = yf.Ticker(ticker)
        # 转换时间格式为 yfinance 需要的日期
        date_str = start_time.strftime('%Y-%m-%d')
        end_date = (start_time + timedelta(days=2)).strftime('%Y-%m-%d')
        
        hist = stock.history(start=date_str, end=end_date)
        if len(hist) >= 2:
            open_price = hist.iloc[0]['Open']
            close_price = hist.iloc[-1]['Close']
            return (close_price - open_price) / open_price
        return None
    except Exception as e:
        print(f"获取 {ticker} 价格失败: {e}")
        return None

def run_analysis():
    print("开始每日准确率分析...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. 找出过去 24-48 小时内的预测记录进行核对
    # (确保已经有足够的时间观察涨跌)
    cur.execute("""
        SELECT id, ticker, sentiment, author, post_time 
        FROM stock_trends 
        WHERE post_time < NOW() - INTERVAL '24 hours' 
        AND post_time > NOW() - INTERVAL '72 hours'
    """)
    
    records = cur.fetchall()
    
    for rec_id, ticker, sentiment, author, post_time in records:
        change = get_price_change(ticker, post_time)
        
        if change is not None:
            # 判断预测是否正确
            is_correct = False
            if sentiment == 'Bullish' and change > 0:
                is_correct = True
            elif sentiment == 'Bearish' and change < 0:
                is_correct = True
            
            # 2. 更新发帖人排名表
            cur.execute("""
                INSERT INTO author_performance (author, total_predictions, correct_predictions)
                VALUES (%s, 1, %s)
                ON CONFLICT (author) DO UPDATE SET
                total_predictions = author_performance.total_predictions + 1,
                correct_predictions = author_performance.correct_predictions + EXCLUDED.correct_predictions,
                accuracy_rate = (CAST(author_performance.correct_predictions + EXCLUDED.correct_predictions AS FLOAT) / 
                                (author_performance.total_predictions + 1)) * 100
            """, (author, 1 if is_correct else 0))

    conn.commit()
    cur.close()
    conn.close()
    print("分析完成！")

if __name__ == "__main__":
    run_analysis()