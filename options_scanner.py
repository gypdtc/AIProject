import os
import yfinance as yf
import google.generativeai as genai
import pandas as pd
import psycopg2
import json

# 配置环境变量
DATABASE_URL = os.getenv("DATABASE_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def run_scanner():
    print("🚀 启动 Whale Flow 扫描协议 (6步过滤)...")
    
    # 监控池：你可以根据需要增减
    watchlist = ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "META", "GOOGL", "NFLX", "COIN", "MARA"]
    final_trades = []

    for ticker in watchlist:
        try:
            stock = yf.Ticker(ticker)
            # Step 1: 扫描 90 天内到期的期权链 (简化为取最近一个到期日)
            expirations = stock.options
            if not expirations: continue
            opts = stock.option_chain(expirations[0])
            
            # 寻找大额成交 (成交额 > $50,000)
            whale_calls = opts.calls[opts.calls['volume'] * opts.calls['lastPrice'] * 100 > 50000]
            
            if not whale_calls.empty:
                # Step 2: 20日均线验证 (趋势对齐)
                hist = stock.history(period="40d")
                sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                curr_price = hist['Close'].iloc[-1]
                
                if curr_price > sma_20:
                    # Step 3: IV 验证 (IV <= 70% 视为不贵)
                    if whale_calls.iloc[0]['impliedVolatility'] <= 0.70:
                        
                        # Step 4: Narrative Check (Gemini 介入)
                        prompt = f"分析股票 {ticker} 最近的新闻。1.未来7天是否有财报或重大法律事件？2.整体情绪是否正面？请严格返回JSON: {{\"score\": 0.8, \"narrative\": \"AI芯片需求强劲\", \"risk\": \"low\"}}"
                        response = model.generate_content(prompt)
                        # 简单清理 response 防止 AI 多嘴
                        clean_json = response.text.strip().replace('```json', '').replace('```', '')
                        ai_result = json.loads(clean_json)
                        
                        if ai_result['risk'] == 'low':
                            # Step 5: Breathing Room (Strike 移近 2%)
                            safe_strike = curr_price * 1.02
                            
                            # Step 6: Final Ranking (模拟公式)
                            final_score = (2.5 + ai_result['score'] - 0.3) # 示例公式
                            
                            final_trades.append({
                                "ticker": ticker,
                                "sentiment": ai_result['score'],
                                "narrative": ai_result['narrative'],
                                "strike": safe_strike,
                                "rr": 2.5,
                                "final_score": final_score
                            })
        except Exception as e:
            print(f"处理 {ticker} 时出错: {e}")

    # 入库
    if final_trades:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        for t in final_trades:
            cur.execute("""
                INSERT INTO option_trades (ticker, sentiment_score, narrative_type, suggested_strike, risk_reward_ratio, final_score)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (t['ticker'], t['sentiment'], t['narrative'], t['strike'], t['rr'], t['final_score']))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 扫描完成，找到 {len(final_trades)} 个高质量机会。")

if __name__ == "__main__":
    run_scanner()