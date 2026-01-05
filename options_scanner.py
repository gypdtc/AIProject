import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime, timedelta
import re

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_json(text):
    try:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        return json.loads(match.group(1)) if match else None
    except: return None

def get_option_expiry(ticker):
    """获取该股票最接近 21 天后的真实到期日"""
    try:
        s = yf.Ticker(ticker)
        expirations = s.options
        if not expirations: return None
        # 寻找距离现在约 21 天左右的周五
        target = next((e for e in expirations if (datetime.strptime(e, '%Y-%m-%d') - datetime.now()).days > 14), expirations[0])
        return target
    except: return None

def run_production_scanner():
    watch_list = ["RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD", 
                  "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META", 
                  "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"]
    
    scan_ts = datetime.now()
    market_dict = {}
    market_block = []

    for t in watch_list:
        try:
            s = yf.Ticker(t)
            p = float(s.fast_info['last_price'])
            info = s.info
            market_dict[t] = {"price": p, "mkt_cap": info.get('marketCap', 0), "expiry": get_option_expiry(t)}
            market_block.append(f"[{t}] 现价: ${p:.2f}")
        except: continue

    # --- AI 逻辑分析 (强制中文风险描述) ---
    prompt = f"""
    分析以下高IV股票原因及卖出Put期权的风险：{list(market_dict.keys())[:10]}。
    要求：
    1. 必须使用【中文】回答。
    2. 针对卖出Put（CSP）策略，评价风险程度（高/中/低）并给出理由。
    返回JSON: {{"iv_reasons": [{{"ticker": "...", "reason": "中文原因", "risk_level": "中文风险评价"}}]}}
    """
    ai_res = extract_json(model.generate_content(prompt).text) or {"iv_reasons": []}

    # --- 数据库入库 ---
    url = urlparse.urlparse(os.getenv("DATABASE_URL"))
    conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
    cur = conn.cursor()

    for item in ai_res['iv_reasons']:
        t = item['ticker']
        if t in market_dict:
            data = market_dict[t]
            # 计算 CSP 建议
            strike = round(data['price'] * 0.88 * 2) / 2
            cur.execute("""
                INSERT INTO public.csp_suggestions 
                (ticker, current_price, suggested_strike, expiration_date, safety_buffer, analysis_logic, scan_timestamp) 
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (t, data['price'], strike, data['expiry'], "12%", item['risk_level'], scan_ts))
            
            # 存入 IV 分析卡片信息
            cur.execute("""
                INSERT INTO public.iv_analysis (ticker, analysis_reason, scan_timestamp, current_price, market_cap) 
                VALUES (%s,%s,%s,%s,%s)
            """, (t, item['reason'], scan_ts, data['price'], data['mkt_cap']))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ 扫描完成")

if __name__ == "__main__":
    run_production_scanner()