import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime
import re # 引入正则用于精确提取 JSON

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_json(text):
    """安全地从 AI 文本中提取 JSON 数组或对象"""
    try:
        # 使用正则匹配最外层的 [ ] 或 { }
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return None
    except:
        return None

def run_production_scanner():
    watch_list = ["RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD", 
                  "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META", 
                  "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"]
    
    scan_time = datetime.now()
    market_data_block = []
    iv_pool = []

    print(f"📡 扫描启动: {scan_time}")

    for ticker in watch_list:
        try:
            s = yf.Ticker(ticker)
            price = s.fast_info['last_price']
            opt_dates = s.options
            avg_iv = 0
            if opt_dates:
                chain = s.option_chain(opt_dates[0])
                avg_iv = float(chain.calls['impliedVolatility'].mean())
                iv_pool.append({"ticker": ticker, "iv": avg_iv})
            
            market_data_block.append(f"[{ticker}] Price: ${price:.2f}, IV: {avg_iv:.2%}")
        except: continue

    # --- 1. 高 IV 专项分析 ---
    top_5_iv = sorted(iv_pool, key=lambda x: x['iv'], reverse=True)[:5]
    if top_5_iv:
        iv_context = ", ".join([f"{x['ticker']}({x['iv']:.1%})" for x in top_5_iv])
        iv_prompt = f"分析这5个高IV股票的原因：{iv_context}。返回JSON格式: [{{'ticker':'...', 'reason':'...'}}]"
        
        iv_response = model.generate_content(iv_prompt)
        # 使用增强解析
        iv_analysis_data = extract_json(iv_response.text)
        
        if not iv_analysis_data:
            print("⚠️ AI 未返回有效 IV 分析 JSON，使用空列表跳过。")
            iv_analysis_data = []
    else:
        iv_analysis_data = []

    # --- 2. 6步协议策略建议 ---
    # 此处省略你之前的 trade_prompt 逻辑，同样使用 extract_json 处理返回
    final_trades = [] # 假设你已经获取并用 extract_json 处理了结果

    # --- 3. 数据库入库 ---
    try:
        url = urlparse.urlparse(os.getenv("DATABASE_URL"))
        conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
        cur = conn.cursor()

        # 写入高 IV 数据
        for item in iv_analysis_data:
            iv_val = next((x['iv'] for x in top_5_iv if x['ticker'] == item['ticker']), 0)
            cur.execute("INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp) VALUES (%s, %s, %s, %s)",
                        (item['ticker'], iv_val, item['reason'], scan_time))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 成功入库 {len(iv_analysis_data)} 条 IV 分析。")
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")

if __name__ == "__main__":
    run_production_scanner()