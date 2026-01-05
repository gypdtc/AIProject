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
    """安全地从 AI 文本中提取 JSON"""
    try:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        return json.loads(match.group(1)) if match else None
    except: return None

def get_option_meta(ticker):
    """抓取该股票最真实且具备流动性的期权到期日"""
    try:
        s = yf.Ticker(ticker)
        expirations = s.options
        if not expirations: return None
        # 选取 DTE > 7 的第一个到期日，避免临期期权干扰
        target_expiry = next((e for e in expirations if (datetime.strptime(e, '%Y-%m-%d') - datetime.now()).days > 7), expirations[0])
        return target_expiry
    except: return None

def get_accurate_iv(ticker):
    """高精度 IV 计算逻辑：过滤掉成交量为0或买卖价差过大的合约"""
    try:
        s = yf.Ticker(ticker)
        price = s.fast_info['last_price']
        target_expiry = get_option_meta(ticker)
        if not target_expiry: return 0
        
        chain = s.option_chain(target_expiry).puts # 参考 Put 链 IV 进行 CSP 评估
        # 过滤：成交量 > 0 且 买卖价差 < 1.0
        valid = chain[(chain['volume'] > 0) & ((chain['ask'] - chain['bid']) < 1.0)].copy()
        if valid.empty: return 0
        
        # 取平值 (ATM) 附近的 6 个合约求平均
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

    print(f"📡 启动全量扫描 (Time: {scan_ts})...")

    for t in watch_list:
        try:
            s = yf.Ticker(t)
            price = float(s.fast_info['last_price'])
            iv = get_accurate_iv(t)
            
            # 只有当 IV 有效时才继续处理该标的，防止后端存入空值
            if iv > 0:
                info = s.info
                expiry = get_option_meta(t)
                market_dict[t] = {
                    "price": price, 
                    "iv": iv, 
                    "expiry": expiry,
                    "mkt_cap": info.get('marketCap', 0)
                }
                news = s.news[:2]
                news_titles = [n['title'] for n in news] if news else ["No recent news"]
                market_block.append(f"[{t}] Price: ${price:.2f}, IV: {iv:.1%}, News: {'; '.join(news_titles)}")
        except Exception as e:
            print(f"跳过 {t}: {e}")

    # --- 1. AI 深度分析 (强制中文 + 风险评估) ---
    prompt = f"""
    作为期权策略专家，基于行情执行分析：
    {chr(10).join(market_block)}
    
    要求：
    1. 【看涨筛选】：基于6步协议，找出所有 Final Score > 7.5 的标的。
    2. 【IV分析】：使用【中文】详细分析高波动原因。
    3. 【风险评估】：使用【中文】评估卖出Put期权(CSP)的风险等级(高/中/低)及理由。
    
    返回 JSON：
    {{
      "trades": [{{ "ticker": "...", "side": "CALL", "final_score": 9.0, "narrative": "中文理由" }}],
      "iv_analysis": [{{ "ticker": "...", "reason": "中文原因", "risk_desc": "中文风险评价" }}]
    }}
    """
    ai_res = extract_json(model.generate_content(prompt).text) or {"trades": [], "iv_analysis": []}

    # --- 2. 数据库写入 ---
    try:
        url = urlparse.urlparse(os.getenv("DATABASE_URL"))
        conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
        cur = conn.cursor()

        # A. 写入 IV 分析与 CSP 建议
        for t in market_dict.keys():
            data = market_dict[t]
            analysis = next((x for x in ai_res['iv_analysis'] if x['ticker'] == t), None)
            
            reason = analysis['reason'] if analysis else "市场波动"
            risk = analysis['risk_desc'] if analysis else "需关注基本面"
            
            # 存入 IV 卡片表
            cur.execute("""
                INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp, current_price, market_cap)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (t, data['iv'], reason, scan_ts, data['price'], data['mkt_cap']))
            
            # 存入 CSP 建议表 (Python 计算行权价)
            strike = round(data['price'] * 0.88 * 2) / 2 # 12% 安全垫
            cur.execute("""
                INSERT INTO public.csp_suggestions (ticker, current_price, suggested_strike, expiration_date, safety_buffer, iv_level, analysis_logic, scan_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (t, data['price'], strike, data['expiry'], "12%", data['iv'], risk, scan_ts))

        # B. 写入策略建议
        for t in ai_res['trades']:
            ticker = t['ticker']
            if ticker in market_dict:
                p = market_dict[ticker]['price']
                strike = round(p * 1.02 * 2) / 2
                exp = (scan_ts + timedelta(days=21)).strftime('%Y-%m-%d')
                cur.execute("""
                    INSERT INTO public.option_trades (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score, scan_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (ticker, t['side'], 0.9, t['narrative'], strike, p, exp, 2.5, t['final_score'], scan_ts))

        conn.commit()
        cur.close()
        conn.close()
        print("✅ 全案入库完成。")
    except Exception as e:
        print(f"❌ 数据库入库失败: {e}")

if __name__ == "__main__":
    run_production_scanner()