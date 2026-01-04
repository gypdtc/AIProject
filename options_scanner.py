import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime
import re

# 1. 配置 Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_json(text):
    """安全地从 AI 文本中提取 JSON"""
    try:
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return None
    except:
        return None

def get_accurate_iv(ticker_symbol):
    """高精度 IV 计算：过滤掉流动性差和极端期限的合约"""
    try:
        s = yf.Ticker(ticker_symbol)
        price = s.fast_info['last_price']
        expirations = s.options
        if not expirations: return 0
        
        # 选取 DTE > 7 天的第一个到期日，避免临期期权干扰
        target_expiry = expirations[0]
        for expiry in expirations:
            days = (datetime.strptime(expiry, '%Y-%m-%d') - datetime.now()).days
            if days > 7:
                target_expiry = expiry
                break
        
        chain = s.option_chain(target_expiry)
        calls = chain.calls
        
        # 过滤：必须有成交量且买卖价差小于 $1.0
        valid_calls = calls[(calls['volume'] > 0) & ((calls['ask'] - calls['bid']) < 1.0)].copy()
        if valid_calls.empty: return 0
        
        # 取平值 (ATM) 附近的 6 个合约求平均，获取最真实的市场 IV
        valid_calls['dist'] = abs(valid_calls['strike'] - price)
        atm_calls = valid_calls.nsmallest(6, 'dist')
        return float(atm_calls['impliedVolatility'].mean())
    except:
        return 0

def run_production_scanner():
    watch_list = ["RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD", 
                  "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META", 
                  "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"]
    
    scan_timestamp = datetime.now()
    market_data_block = []
    iv_pool = []

    print(f"📡 启动高精度扫描: {scan_timestamp}")

    for ticker in watch_list:
        try:
            s = yf.Ticker(ticker)
            price = s.fast_info['last_price']
            # 使用高精度 IV 函数
            precise_iv = get_accurate_iv(ticker)
            if precise_iv > 0:
                iv_pool.append({"ticker": ticker, "iv": precise_iv})
            
            news = s.news[:2]
            news_titles = [n['title'] for n in news] if news else ["No recent news"]
            market_data_block.append(f"[{ticker}] Price: ${price:.2f}, IV: {precise_iv:.2%}, News: {'; '.join(news_titles)}")
        except Exception as e:
            print(f"跳过 {ticker}: {e}")

    # --- 1. 高 IV 原因分析 (Top 5) ---
    top_5_iv = sorted(iv_pool, key=lambda x: x['iv'], reverse=True)[:5]
    iv_analysis_data = []
    if top_5_iv:
        iv_context = ", ".join([f"{x['ticker']}({x['iv']:.1%})" for x in top_5_iv])
        prompt = f"分析这些高IV股票的原因：{iv_context}。必须返回JSON: [{{'ticker':'...', 'reason':'...'}}]"
        res = model.generate_content(prompt)
        iv_analysis_data = extract_json(res.text) or []

    # --- 2. 6步协议策略建议 ---
    trade_prompt = f"""
    基于以下数据执行 6 步协议（Whale Flow, Trend, IV, Narrative, Structure, Math Score）：
    {chr(10).join(market_data_block)}
    返回JSON: [{{'ticker':'...', 'side':'CALL', 'sentiment_score':0.9, 'narrative_type':'...', 'suggested_strike':100.0, 'entry_stock_price':95.0, 'expiration_date':'2026-02-01', 'risk_reward_ratio':2.5, 'final_score':8.5}}]
    """
    trade_res = model.generate_content(trade_prompt)
    final_trades = extract_json(trade_res.text) or []

    # --- 3. 数据库写入 ---
    try:
        url = urlparse.urlparse(os.getenv("DATABASE_URL"))
        conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
        cur = conn.cursor()

        # 写入 IV 分析
        for item in iv_analysis_data:
            iv_val = next((x['iv'] for x in top_5_iv if x['ticker'] == item['ticker']), 0)
            cur.execute("INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp) VALUES (%s, %s, %s, %s)",
                        (item['ticker'], iv_val, item['reason'], scan_timestamp))
        
        # 写入策略建议
        for t in final_trades:
            cur.execute("""
                INSERT INTO public.option_trades (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score, scan_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (t['ticker'], t['side'], t['sentiment_score'], t['narrative_type'], t['suggested_strike'], t['entry_stock_price'], t['expiration_date'], t['risk_reward_ratio'], t['final_score'], scan_timestamp))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 扫描完成：{len(iv_analysis_data)} 条IV分析, {len(final_trades)} 条交易建议。")
    except Exception as e:
        print(f"❌ 数据库错误: {e}")

if __name__ == "__main__":
    run_production_scanner()