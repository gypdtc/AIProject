import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse

# 1. 基础配置
DATABASE_URL = os.getenv("DATABASE_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def get_db_connection():
    parsed = urlparse.urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=parsed.path[1:].split('?')[0],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        sslmode='require'
    )
    with conn.cursor() as cur:
        cur.execute("SET search_path TO public;")
    return conn

def run_scanner():
    print("🚀 启动 Whale Flow 增强版扫描协议...")
    watchlist = ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "META", "GOOGL", "NFLX", "COIN", "MARA"]
    final_trades = []

    for ticker in watchlist:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if hist.empty: continue
            curr_price = float(hist['Close'].iloc[-1])
            
            # Step 1: 扫描期权链
            expirations = stock.options
            if not expirations: continue
            opts = stock.option_chain(expirations[0])
            
            # 这里的逻辑可以根据异动量筛选，这里为了演示保留逻辑
            # 调用 AI 进行方向和叙事判断
            prompt = f"""
            分析股票 {ticker} 的近期趋势。当前价格 ${curr_price:.2f}。
            请给出未来7天的操作建议：
            1. 应该是看涨(CALL)还是看跌(PUT)?
            2. 给出一个信心评分 (0-1.0)。
            3. 详细解释原因（Narrative）。
            请严格返回JSON格式，不要有其他文字：
            {{"side": "CALL", "score": 0.85, "narrative": "这里写详细原因"}}
            """
            response = model.generate_content(prompt)
            clean_json = response.text.strip().replace('```json', '').replace('```', '')
            ai_result = json.loads(clean_json)
            
            # 记录数据
            final_trades.append({
                "ticker": ticker,
                "side": ai_result.get('side', 'CALL'),
                "sentiment": float(ai_result.get('score', 0.5)),
                "narrative": str(ai_result.get('narrative', '')),
                "strike": float(curr_price * (1.02 if ai_result.get('side') == 'CALL' else 0.98)),
                "entry_price": curr_price,
                "final_score": float(ai_result.get('score', 0.5) * 10)
            })
            print(f"✅ 已分析 {ticker}: {ai_result.get('side')}")

        except Exception as e:
            print(f"⚠️ {ticker} 异常: {e}")

    # 写入数据库
    if final_trades:
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            for t in final_trades:
                cur.execute("""
                    INSERT INTO public.option_trades 
                    (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, final_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (t['ticker'], t['side'], t['sentiment'], t['narrative'], t['strike'], t['entry_price'], t['final_score']))
            conn.commit()
            print(f"💰 成功入库 {len(final_trades)} 条建议。")
        except Exception as e:
            print(f"❌ 写入失败: {e}")
        finally:
            if conn: conn.close()

if __name__ == "__main__":
    run_scanner()