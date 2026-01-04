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
        if match:
            return json.loads(match.group(1))
        return None
    except:
        return None

def get_accurate_iv(ticker_symbol):
    try:
        s = yf.Ticker(ticker_symbol)
        price = s.fast_info['last_price']
        expirations = s.options
        if not expirations: return 0
        target_expiry = expirations[0]
        for expiry in expirations:
            days = (datetime.strptime(expiry, '%Y-%m-%d') - datetime.now()).days
            if days > 7:
                target_expiry = expiry
                break
        chain = s.option_chain(target_expiry)
        calls = chain.calls
        valid_calls = calls[(calls['volume'] > 0) & ((calls['ask'] - calls['bid']) < 1.0)].copy()
        if valid_calls.empty: return 0
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
    market_data_dict = {} # 使用字典存储，方便后续 Python 计算
    market_data_block = []

    print(f"📡 启动高精度扫描: {scan_timestamp}")

    for ticker in watch_list:
        try:
            s = yf.Ticker(ticker)
            price = float(s.fast_info['last_price'])
            precise_iv = get_accurate_iv(ticker)
            
            news = s.news[:2]
            news_titles = [n['title'] for n in news] if news else ["No recent news"]
            market_data_block.append(f"[{ticker}] Price: ${price:.2f}, IV: {precise_iv:.2%}, News: {'; '.join(news_titles)}")
            
            # 存储实时价格用于后续逻辑校验
            market_data_dict[ticker] = {"price": price, "iv": precise_iv}
        except Exception as e:
            print(f"跳过 {ticker}: {e}")

    # --- 1. 高 IV 分析 ---
    iv_pool = [{"ticker": k, "iv": v["iv"]} for k, v in market_data_dict.items() if v["iv"] > 0]
    top_5_iv = sorted(iv_pool, key=lambda x: x['iv'], reverse=True)[:5]
    iv_analysis_data = []
    if top_5_iv:
        iv_context = ", ".join([f"{x['ticker']}({x['iv']:.1%})" for x in top_5_iv])
        prompt = f"分析这些高IV股票的原因：{iv_context}。必须返回JSON: [{{'ticker':'...', 'reason':'...'}}]"
        res = model.generate_content(prompt)
        iv_analysis_data = extract_json(res.text) or []

    # --- 2. 6步协议策略建议 (优化 Prompt 提高产出) ---
    trade_prompt = f"""
    作为专业期权交易员，请对以下标的执行 6 步量化协议：
    {chr(10).join(market_data_block)}
    
    指令：
    1. 评估每个标的的 Narrative Score (-1 到 1)。
    2. 计算 Final Score (0-10)。
    3. 找出所有 Final Score > 7.0 的标的，不要只给一个。
    
    必须严格返回 JSON 数组（不要包含计算 Strike 的逻辑，只需给出评分和叙事）：
    [{{
        "ticker": "NVDA", 
        "side": "CALL", 
        "sentiment_score": 0.9, 
        "narrative_type": "叙事简述", 
        "risk_reward_ratio": 2.5, 
        "final_score": 8.5
    }}]
    """
    trade_res = model.generate_content(trade_prompt)
    ai_trades = extract_json(trade_res.text) or []

    # --- 3. 核心修复：Python 强校验入库 ---
    try:
        url = urlparse.urlparse(os.getenv("DATABASE_URL"))
        conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
        cur = conn.cursor()

        # 写入 IV 分析
        for item in iv_analysis_data:
            iv_val = next((x['iv'] for x in top_5_iv if x['ticker'] == item['ticker']), 0)
            cur.execute("INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp) VALUES (%s, %s, %s, %s)",
                        (item['ticker'], iv_val, item['reason'], scan_timestamp))
        
        # 写入策略建议 (Python 计算 Strike 和 Expiration)
        for t in ai_trades:
            ticker = t['ticker']
            if ticker in market_data_dict:
                real_price = market_data_dict[ticker]['price']
                
                # --- 修复逻辑：强制计算 ---
                # 1. 行权价 = 市价 * 1.02，并向下取整到 0.5
                suggested_strike = round(real_price * 1.02 * 2) / 2
                # 2. 到期日 = 今天 + 21 天
                expiration_date = (scan_timestamp + timedelta(days=21)).strftime('%Y-%m-%d')
                
                cur.execute("""
                    INSERT INTO public.option_trades 
                    (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score, scan_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (ticker, t['side'], t['sentiment_score'], t['narrative_type'], suggested_strike, real_price, expiration_date, t['risk_reward_ratio'], t['final_score'], scan_timestamp))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 扫描完成。建议数: {len(ai_trades)}。")
    except Exception as e:
        print(f"❌ 数据库错误: {e}")

if __name__ == "__main__":
    run_production_scanner()