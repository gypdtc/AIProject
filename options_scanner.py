import os
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse

# 1. 配置 Gemini 2.5 Flash 及其搜索工具
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 启用 Google Search 实时工具，这是让 AI "睁眼看世界" 的核心
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[{"google_search": {}}] 
)

def run_ai_agent_scanner():
    print("🤖 AI 代理启动：正在全网扫描 Whale Flow (执行 6 步协议)...")
    
    # 你的核心 Prompt：直接将 6 步量化协议作为 AI 指令
    prompt = """
    请作为一名高级期权量化交易员，利用实时搜索功能，严格执行以下 6 步筛选协议，找出今日（2026年1月2日）美股最强信号：

    Step 1: 扫描全市场单笔溢价 > $50k、90天内到期的期权流，识别标的和方向。
    Step 2: 对这些标的进行趋势对齐，仅保留 Call 远超 Put 且价格在 20日均线 (SMA) 之上的标的。
    Step 3: 检查 IV Rank，剔除 IVR > 70 的昂贵标的，仅保留估值合理的合约。
    Step 4: 叙事核查。搜索未来 7 天内是否有财报或负面新闻，给出情绪评分 (-1 到 1) 和 Narrative Type。
    Step 5: 结构优化 (Breathing Room)。行权价调整至市价 2% 以内，到期日延长 14 天。
    Step 6: 数学评分。计算 Risk/Reward 比例，仅保留比值 > 2 的交易。

    请严格返回符合条件的 Top 5 交易，输出必须是纯 JSON 数组格式，禁止任何解释文字：
    [{"ticker": "NVDA", "side": "CALL", "score": 0.85, "narrative": "AI需求超预期", "strike": 145.0, "expiration": "2026-02-15", "entry_price": 140.0, "rr": 2.5, "final_score": 8.5}]
    """

    try:
        # AI 进行思考和搜索
        response = model.generate_content(prompt)
        
        # 清理响应内容并解析 JSON
        raw_text = response.text.strip().replace('```json', '').replace('```', '')
        final_trades = json.loads(raw_text)
        
        if final_trades:
            # 数据库连接逻辑（保持你原来的参数化连接方式以解决 np 报错）
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
                """, (t['ticker'], t['side'], t['score'], t['narrative'], t['strike'], t['entry_price'], t['expiration'], t['rr'], t['final_score']))
            
            conn.commit()
            print(f"✅ AI 代理完成，成功入库 {len(final_trades)} 条深度筛选出的机会。")
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"❌ AI 扫描或入库失败: {e}")

if __name__ == "__main__":
    run_ai_agent_scanner()