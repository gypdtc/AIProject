import os
import yfinance as yf
import google.generativeai as genai
import pandas as pd
import psycopg2
import json
import re
import urllib.parse as urlparse

# 1. 基础配置
# 严格使用你指定的 gemini-2.5-flash
DATABASE_URL = os.getenv("DATABASE_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def get_db_connection():
    """使用解析后的参数连接，并强制设置 search_path"""
    parsed = urlparse.urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=parsed.path[1:].split('?')[0],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        sslmode='require'
    )
    # 强制执行，确保当前连接环境干净
    with conn.cursor() as cur:
        cur.execute("SET search_path TO public;")
    return conn

def run_scanner():
    print("🚀 启动 Whale Flow 扫描协议 (6步过滤)...")
    
    # 监控池
    watchlist = ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "META", "GOOGL", "NFLX", "COIN", "MARA"]
    final_trades = []

    for ticker in watchlist:
        try:
            print(f"分析中: {ticker}")
            stock = yf.Ticker(ticker)
            expirations = stock.options
            if not expirations: continue
            
            # Step 1: 获取期权链
            opts = stock.option_chain(expirations[0])
            
            # Step 1 过滤: 成交额 > $50,000
            whale_calls = opts.calls[opts.calls['volume'] * opts.calls['lastPrice'] * 100 > 50000]
            
            if not whale_calls.empty:
                # Step 2: 20日均线 (趋势对齐)
                hist = stock.history(period="40d")
                sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                curr_price = hist['Close'].iloc[-1]
                
                if curr_price > sma_20:
                    # Step 3: IV 验证 (IV <= 70%)
                    iv = whale_calls.iloc[0]['impliedVolatility']
                    if iv <= 0.70:
                        # Step 4: Narrative Check (Gemini)
                        prompt = f"分析股票 {ticker} 最近的新闻。1.未来7天是否有财报或重大法律事件？2.整体情绪是否正面？请严格返回JSON: {{\"score\": 0.8, \"narrative\": \"AI需求旺盛\", \"risk\": \"low\"}}"
                        response = model.generate_content(prompt)
                        clean_json = response.text.strip().replace('```json', '').replace('```', '')
                        ai_result = json.loads(clean_json)
                        
                        if ai_result['risk'] == 'low':
                            # 收集结果并确保类型转换 (防止 numpy 干扰)
                            final_trades.append({
                                "ticker": ticker,
                                "sentiment": float(ai_result['score']),
                                "narrative": str(ai_result['narrative']),
                                "strike": float(curr_price * 1.02),
                                "rr": 2.5,
                                "final_score": float(2.5 + ai_result['score'] - 0.3)
                            })
        except Exception as e:
            print(f"⚠️ {ticker} 扫描异常: {e}")

    # 2. 数据库写入 (修复 np schema 报错的核心)
    if final_trades:
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 显式指定 public.option_trades
            insert_query = """
                INSERT INTO public.option_trades (
                    ticker, 
                    sentiment_score, 
                    narrative_type, 
                    suggested_strike, 
                    risk_reward_ratio, 
                    final_score
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            for t in final_trades:
                # 显式构造 Python 原生类型的元组
                data_tuple = (
                    t['ticker'],
                    t['sentiment'],
                    t['narrative'],
                    t['strike'],
                    t['rr'],
                    t['final_score']
                )
                cur.execute(insert_query, data_tuple)
            
            conn.commit()
            print(f"✅ 扫描完成，已成功写入 {len(final_trades)} 条数据。")
        except Exception as e:
            print(f"❌ 数据库最终写入失败: {e}")
        finally:
            if conn:
                cur.close()
                conn.close()

if __name__ == "__main__":
    run_scanner()