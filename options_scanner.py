import os
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse

# 1. 配置 Gemini 2.5 Flash
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 根据报错 400 的明确指示：使用 google_search 而不是 google_search_retrieval
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[{"google_search": {}}] # 恢复为报错要求的字段名
)

def run_ai_agent_scanner():
    print("🤖 AI 代理启动：正在使用 Google Search 扫描 Whale Flow...")
    
    # 你的 6 步量化协议 Prompt
    prompt = """
    请作为高级期权量化交易员，利用实时搜索功能，严格执行以下 6 步筛选协议，找出今日美股最强信号：

    Step 1 (Scanning): 扫描全市场单笔溢价 > $50k、90天内到期的期权流。
    Step 2 (Filter): 仅保留趋势对齐（价格在 20日 SMA 之上）的 Bullish Flow。
    Step 3 (IV Check): 剔除 IV Rank > 70 的昂贵标的。
    Step 4 (Narrative): 搜索未来 7 天内是否有财报或负面新闻，给出情绪评分 (-1 到 1)。
    Step 5 (Structuring): 行权价调整至市价 2% 以内，到期日延长 14 天。
    Step 6 (Math Check): 确保 Risk/Reward > 2。

    请严格返回 JSON 数组格式，对接以下数据库字段名：
    [{"ticker": "NVDA", "side": "CALL", "sentiment_score": 0.85, "narrative_type": "AI需求超预期...", "suggested_strike": 145.0, "entry_stock_price": 140.0, "expiration_date": "2026-02-15", "risk_reward_ratio": 2.5, "final_score": 8.5}]
    """

    try:
        # 调用 AI 生成内容
        response = model.generate_content(prompt)
        
        # 稳健的 JSON 提取逻辑
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0]
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0]
        
        final_trades = json.loads(raw_text.strip())
        
        if final_trades:
            # 数据库连接 (参数化方式防止 np 报错)
            url = urlparse.urlparse(os.getenv("DATABASE_URL"))
            conn = psycopg2.connect(
                database=url.path[1:], user=url.username, password=url.password,
                host=url.hostname, port=url.port, sslmode='require'
            )
            cur = conn.cursor()
            
            for t in final_trades:
                try:
                    # 确保日期格式正确 (YYYY-MM-DD)
                    cur.execute("""
                        INSERT INTO public.option_trades 
                        (ticker, side, sentiment_score, narrative_type, suggested_strike, entry_stock_price, expiration_date, risk_reward_ratio, final_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        t['ticker'], t['side'], t['sentiment_score'], t['narrative_type'], 
                        t['suggested_strike'], t['entry_stock_price'], t['expiration_date'], 
                        t['risk_reward_ratio'], t['final_score']
                    ))
                except Exception as row_e:
                    print(f"⚠️ 跳过 {t.get('ticker')}: {row_e}")
                    conn.rollback()
                else:
                    conn.commit()
            
            print(f"✅ 扫描成功：已入库 {len(final_trades)} 条符合 6 步协议的建议。")
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"❌ 运行失败详情: {e}")

if __name__ == "__main__":
    run_ai_agent_scanner()