import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse

# 1. 配置 Gemini (不带 tools 参数，最稳)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def run_stable_scanner():
    watch_list = [
        "RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD",
        "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META",
        "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"
    ]
    
    print(f"📡 正在获取 {len(watch_list)} 只股票的实时行情数据...")
    
    # 获取基础行情，解决 AI 价格幻觉问题
    market_context = []
    for ticker in watch_list:
        try:
            s = yf.Ticker(ticker)
            price = s.fast_info['last_price']
            market_context.append(f"{ticker}: ${price:.2f}")
        except: continue

    # 2. 构建 Prompt：把行情数据直接喂给 AI
    prompt = f"""
    作为高级期权策略专家，基于以下实时股价，执行 6 步量化协议筛选建议：
    实时行情：{', '.join(market_context)}

    协议：
    Step 1: 扫描这些标的大额期权异动 (Premium > $50k)。
    Step 2: 确认趋势对齐（需在 20日 SMA 之上）。
    Step 3: 检查 IV Rank (须 <= 70)。
    Step 4: 叙事核查。搜索并判断未来 7 天是否有财报或重大利空。
    Step 5: 结构调整。行权价调至市价 2% 内，到期日延 14 天。
    Step 6: Risk/Reward > 2。

    必须严格返回 JSON 数组格式（不要任何文字说明）：
    [
      {{
        "ticker": "NVDA", 
        "side": "CALL", 
        "sentiment_score": 0.9, 
        "narrative_type": "叙事理由", 
        "suggested_strike": 145.0, 
        "entry_stock_price": 141.2, 
        "expiration_date": "2026-01-20", 
        "risk_reward_ratio": 2.5, 
        "final_score": 8.8
      }}
    ]
    """

    try:
        # 此时 Gemini 会利用其内部训练数据和强大的逻辑能力进行分析
        response = model.generate_content(prompt)
        raw_text = response.text.strip().replace('```json', '').replace('```', '')
        final_trades = json.loads(raw_text)
        
        if final_trades:
            url = urlparse.urlparse(os.getenv("DATABASE_URL"))
            conn = psycopg2.connect(
                database=url.path[1:], user=url.username, password=url.password,
                host=url.hostname, port=url.port, sslmode='require'
            )
            cur = conn.cursor()
            
            for t in final_trades:
                cur.execute("""
                    INSERT INTO public.option_trades 
                    (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    t['ticker'], t['side'], t['sentiment_score'], t['narrative_type'], 
                    t['suggested_strike'], t['entry_stock_price'], t['expiration_date'], 
                    t['risk_reward_ratio'], t['final_score']
                ))
            conn.commit()
            print(f"✅ 已完成 {len(final_trades)} 条建议的入库。")
            cur.close()
            conn.close()
    except Exception as e:
        print(f"❌ 运行失败: {e}")

if __name__ == "__main__":
    run_stable_scanner()