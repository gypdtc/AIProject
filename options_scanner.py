import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime, timedelta
import re

# 1. 配置 Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_json(text):
    try:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        return json.loads(match.group(1)) if match else None
    except: return None

def get_accurate_iv(ticker):
    try:
        s = yf.Ticker(ticker)
        price = s.fast_info['last_price']
        exp = s.options
        if not exp: return 0
        target = next((e for e in exp if (datetime.strptime(e, '%Y-%m-%d') - datetime.now()).days > 7), exp[0])
        chain = s.option_chain(target).puts 
        valid = chain[(chain['volume'] > 0) & ((chain['ask'] - chain['bid']) < 1.0)].copy()
        if valid.empty: return 0
        valid['dist'] = abs(valid['strike'] - price)
        return float(valid.nsmallest(6, 'dist')['impliedVolatility'].mean())
    except: return 0

def run_production_scanner():
    watch_list = ["RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD", 
                  "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META", 
                  "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"]
    
    scan_ts = datetime.now()
    market_dict = {}
    market_block = []

    print(f"📡 启动深度扫描...")

    for t in watch_list:
        try:
            s = yf.Ticker(t)
            info = s.info # 获取基础财务数据
            p = float(s.fast_info['last_price'])
            iv = get_accurate_iv(t)
            mkt_cap = info.get('marketCap', 0)
            
            market_dict[t] = {"price": p, "iv": iv, "mkt_cap": mkt_cap}
            news = s.news[:2]
            market_block.append(f"[{t}] Price: ${p:.2f}, IV: {iv:.1%}, News: {'; '.join([n['title'] for n in news])}")
        except: continue

    # --- 1. AI 执行逻辑分析 (强制中文) ---
    prompt = f"""
    你是高级量化分析师。基于以下行情：
    {chr(10).join(market_block)}
    
    任务：
    1. 【看涨筛选】：基于6步协议，找出所有 Final Score > 7.5 的标的。
    2. 【IV分析】：找出 IV 最高的 10 只股票，并用中文分析其高波动原因。
    
    必须返回 JSON 格式：
    {{
      "trades": [{{ "ticker": "NVDA", "side": "CALL", "final_score": 9.0, "narrative_type": "中文理由" }}],
      "iv_reasons": [{{ "ticker": "ONDS", "reason": "中文解释" }}]
    }}
    """
    ai_res = extract_json(model.generate_content(prompt).text) or {"trades": [], "iv_reasons": []}

    # --- 2. 数据库入库 ---
    url = urlparse.urlparse(os.getenv("DATABASE_URL"))
    conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
    cur = conn.cursor()

    # A. 存入 CSP 建议 & IV 分析 (前 10 名)
    top_10_iv = sorted([{"t": k, "iv": v["iv"]} for k, v in market_dict.items()], key=lambda x: x['iv'], reverse=True)[:10]
    for item in top_10_iv:
        t = item['t']
        data = market_dict[t]
        reason = next((x['reason'] for x in ai_res['iv_reasons'] if x['ticker'] == t), "市场高波动")
        strike = round(data['price'] * 0.88 * 2) / 2
        cur.execute("""
            INSERT INTO public.csp_suggestions (ticker, current_price, suggested_strike, safety_buffer, iv_level, analysis_logic, scan_timestamp) 
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (t, data['price'], strike, "12%", item['iv'], reason, scan_ts))
        
        # 存入 IV 分析表 (包含新增字段)
        cur.execute("""
            INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp, current_price, market_cap) 
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (t, item['iv'], reason, scan_ts, data['price'], data['mkt_cap']))

    # B. 存入看涨建议 (自动计算)
    for t in ai_res['trades']:
        ticker = t['ticker']
        if ticker in market_dict:
            p = market_dict[ticker]['price']
            strike = round(p * 1.02 * 2) / 2
            exp = (scan_ts + timedelta(days=21)).strftime('%Y-%m-%d')
            cur.execute("INSERT INTO public.option_trades (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score, scan_timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (ticker, t['side'], 0.9, t['narrative_type'], strike, p, exp, 2.5, t['final_score'], scan_ts))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ 扫描完成。")

if __name__ == "__main__":
    run_production_scanner()