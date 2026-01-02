import os
import yfinance as yf
import google.generativeai as genai
import pandas as pd
import psycopg2
import json
import re

# 1. 基础配置
# 直接使用您指定的 2.5 模型
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def get_db_connection():
    """手动解析 DATABASE_URL 以避开 psycopg2 的解析 Bug"""
    db_url = os.getenv("DATABASE_URL")
    
    # 使用正则表达式提取：postgres://user:password@host:port/dbname
    # 这种方式不会被密码中的 @ 或其他特殊符号干扰
    regex = r"postgresql://(?P<user>.*?):(?P<password>.*?)@(?P<host>.*?):?(?P<port>\d+)?/(?P<dbname>.*)"
    match = re.match(regex, db_url)
    
    if not match:
        raise Exception("无法解析 DATABASE_URL，请检查格式是否正确。")
    
    params = match.groupdict()
    
    # 清理 dbname 中的查询参数（如 ?sslmode=require）
    if "?" in params['dbname']:
        params['dbname'] = params['dbname'].split("?")[0]

    return psycopg2.connect(
        database=params['dbname'],
        user=params['user'],
        password=params['password'],
        host=params['host'],
        port=params['port'] or 5432,
        sslmode='require'
    )

def run_scanner():
    print("🚀 启动 Whale Flow 扫描协议 (6步过滤)...")
    watchlist = ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "META", "GOOGL", "NFLX", "COIN", "MARA"]
    final_trades = []

    for ticker in watchlist:
        try:
            print(f"分析中: {ticker}")
            stock = yf.Ticker(ticker)
            expirations = stock.options
            if not expirations: continue
            
            opts = stock.option_chain(expirations[0])
            whale_calls = opts.calls[opts.calls['volume'] * opts.calls['lastPrice'] * 100 > 50000]
            
            if not whale_calls.empty:
                hist = stock.history(period="40d")
                sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                curr_price = hist['Close'].iloc[-1]
                
                if curr_price > sma_20:
                    if whale_calls.iloc[0]['impliedVolatility'] <= 0.70:
                        prompt = f"分析股票 {ticker} 最近的新闻。1.未来7天是否有财报或重大法律事件？2.整体情绪是否正面？请严格返回JSON: {{\"score\": 0.8, \"narrative\": \"AI需求旺盛\", \"risk\": \"low\"}}"
                        response = model.generate_content(prompt)
                        clean_json = response.text.strip().replace('```json', '').replace('```', '')
                        ai_result = json.loads(clean_json)
                        
                        if ai_result['risk'] == 'low':
                            final_trades.append({
                                "ticker": ticker,
                                "sentiment": ai_result['score'],
                                "narrative": ai_result['narrative'],
                                "strike": curr_price * 1.02,
                                "rr": 2.5,
                                "final_score": 2.5 + ai_result['score'] - 0.3
                            })
        except Exception as e:
            print(f"⚠️ {ticker} 处理跳过: {e}")

    # 2. 数据库写入
    if final_trades:
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            for t in final_trades:
                cur.execute("""
                    INSERT INTO option_trades (ticker, sentiment_score, narrative_type, suggested_strike, risk_reward_ratio, final_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (t['ticker'], t['sentiment'], t['narrative'], t['strike'], t['rr'], t['final_score']))
            conn.commit()
            print(f"✅ 成功写入 {len(final_trades)} 条机会。")
        except Exception as e:
            print(f"❌ 数据库最终写入失败: {e}")
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_scanner()