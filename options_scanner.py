import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime, timedelta
import re

# 1. 配置 Gemini 2.5 Flash
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_json(text):
    try:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        return json.loads(match.group(1)) if match else None
    except: return None

def get_accurate_iv(ticker):
    """高精度 IV 计算逻辑"""
    try:
        s = yf.Ticker(ticker)
        price = s.fast_info['last_price']
        exp = s.options
        if not exp: return 0
        # 选取 DTE > 7 的合约，避免临期波动
        target = next((e for e in exp if (datetime.strptime(e, '%Y-%m-%d') - datetime.now()).days > 7), exp[0])
        chain = s.option_chain(target).puts # 注意：为了 CSP，我们可以参考 Put 链的 IV
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

    print(f"📡 启动双策略扫描 (Buy Call & Sell Put)...")

    for t in watch_list:
        try:
            s = yf.Ticker(t)
            p = float(s.fast_info['last_price'])
            iv = get_accurate_iv(t)
            market_dict[t] = {"price": p, "iv": iv}
            news = s.news[:2]
            market_block.append(f"[{t}] Price: ${p:.2f}, IV: {iv:.1%}, News: {'; '.join([n['title'] for n in news])}")
        except: continue

    # --- 1. AI 执行逻辑分析 ---
    prompt = f"""
    你是高级量化分析师。基于以下行情：
    {chr(10).join(market_block)}
    
    任务：
    1. 【看涨筛选】：基于6步协议，找出所有 Final Score > 7.5 的标的。
    2. 【IV分析】：找出 IV 最高的 5 只股票，分析其高波动原因。
    
    必须返回 JSON 格式：
    {{
      "trades": [{{ "ticker": "NVDA", "side": "CALL", "final_score": 9.0, "narrative_type": "AI需求" }}],
      "iv_reasons": [{{ "ticker": "ONDS", "reason": "财报预期" }}]
    }}
    """
    ai_res = extract_json(model.generate_content(prompt).text) or {"trades": [], "iv_reasons": []}

    # --- 2. 数据库入库逻辑 (强制 Python 计算行权价) ---
    url = urlparse.urlparse(os.getenv("DATABASE_URL"))
    conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
    cur = conn.cursor()

    # A. 存入 CSP 建议 (针对高 IV 标的)
    top_5_iv = sorted([{"t": k, "iv": v["iv"]} for k, v in market_dict.items()], key=lambda x: x['iv'], reverse=True)[:5]
    for item in top_5_iv:
        t = item['t']
        p = market_dict[t]['price']
        reason = next((x['reason'] for x in ai_res['iv_reasons'] if x['ticker'] == t), "市场高波动")
        # CSP 逻辑：行权价设在市价 -12%
        strike = round(p * 0.88 * 2) / 2
        cur.execute("INSERT INTO public.csp_suggestions (ticker, current_price, suggested_strike, safety_buffer, iv_level, analysis_logic, scan_timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (t, p, strike, "12%", item['iv'], reason, scan_ts))

    # B. 存入看涨建议
    for t in ai_res['trades']:
        ticker = t['ticker']
        if ticker in market_dict:
            p = market_dict[ticker]['price']
            strike = round(p * 1.02 * 2) / 2 # 看涨设在 +2%
            exp = (scan_ts + timedelta(days=21)).strftime('%Y-%m-%d')
            cur.execute("INSERT INTO public.option_trades (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score, scan_timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (ticker, t['side'], 0.9, t['narrative_type'], strike, p, exp, 2.5, t['final_score'], scan_ts))

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ 完成入库。建议: {len(ai_res['trades'])}条, CSP: {len(top_5_iv)}条。")

if __name__ == "__main__":
    run_production_scanner()