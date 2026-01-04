import os
import yfinance as yf
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse
from datetime import datetime

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

def run_production_scanner():
    watch_list = ["RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD", 
                  "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META", 
                  "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"]
    
    scan_time = datetime.now()
    market_data_block = []
    iv_list = []

    print(f"📡 扫描启动时间: {scan_time}")

    for ticker in watch_list:
        try:
            s = yf.Ticker(ticker)
            price = s.fast_info['last_price']
            # 获取期权链并计算平均 IV
            opt_dates = s.options
            if opt_dates:
                chain = s.option_chain(opt_dates[0])
                avg_iv = chain.calls['impliedVolatility'].mean()
                iv_list.append({"ticker": ticker, "iv": avg_iv})
            
            news = s.news[:2]
            news_titles = [n['title'] for n in news] if news else ["No recent news"]
            market_data_block.append(f"[{ticker}] Price: ${price:.2f}, IV: {avg_iv:.2%}, News: {'; '.join(news_titles)}")
        except: continue

    # 1. 筛选 Top 5 高 IV 股票并让 AI 分析
    top_5_iv = sorted(iv_list, key=lambda x: x['iv'], reverse=True)[:5]
    iv_tickers = [x['ticker'] for x in top_5_iv]
    
    iv_prompt = f"分析以下高IV股票：{', '.join(iv_tickers)}。请结合近期新闻，简述为什么这些股票的隐含波动率(IV)如此之高。返回格式：[{{'ticker':'...', 'reason':'...'}}]"
    iv_response = model.generate_content(iv_prompt)
    iv_analysis_data = json.loads(iv_analysis_data_raw := iv_response.text.strip().replace('```json', '').replace('```', ''))

    # 2. 执行原有的 6 步量化协议建议 (省略部分重复逻辑)
    # ... 发送原有的 prompt 并获取 final_trades ...

    # 3. 统一入库
    url = urlparse.urlparse(os.getenv("DATABASE_URL"))
    conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port, sslmode='require')
    cur = conn.cursor()

    # 存入高 IV 分析
    for item in iv_analysis_data:
        cur.execute("INSERT INTO public.iv_analysis (ticker, iv_value, analysis_reason, scan_timestamp) VALUES (%s, %s, %s, %s)",
                    (item['ticker'], next(x['iv'] for x in top_5_iv if x['ticker'] == item['ticker']), item['reason'], scan_time))
    
    # 存入正式建议 (增加 scan_timestamp)
    # cur.execute("INSERT INTO public.option_trades (... scan_timestamp) VALUES (... %s)", (..., scan_time))
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ 扫描与高 IV 专项分析已同步入库。")

if __name__ == "__main__":
    run_production_scanner()