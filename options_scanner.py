import os
import google.generativeai as genai
import psycopg2
import json
import urllib.parse as urlparse

# 1. 配置 Gemini 2.5 Flash
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 启用实时搜索工具
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[{"google_search": {}}]
)

def run_targeted_scanner():
    # 你提供的指定观察清单
    watch_list = [
        "RKLB", "ASTS", "AMZN", "NBIS", "GOOGL", "RDDT", "MU", "SOFI", "POET", "AMD",
        "IREN", "HOOD", "RIVN", "NVDA", "ONDS", "LUNR", "APLD", "TSLA", "PLTR", "META",
        "NVO", "AVGO", "PATH", "PL", "NFLX", "OPEN", "ANIC", "TMC", "FNMA", "UBER"
    ]
    
    print(f"🎯 目标扫描启动：正在对清单内的 {len(watch_list)} 个标的执行 6 步协议分析...")
    
    # 修改 Prompt，明确要求只分析这个清单
    prompt = f"""
    作为高级期权量化交易员，请利用实时搜索功能，仅针对以下股票清单进行 6 步量化分析：
    清单: {', '.join(watch_list)}

    执行协议：
    Step 1: 检查这些标的今日是否有单笔溢价 > $50k、90天内到期的期权异动。
    Step 2: 验证趋势。保留价格在 20日 SMA 之上且 Call 流占优的标的。
    Step 3: 检查 IV Rank。剔除 IVR > 70 的标的。
    Step 4: 叙事核查。搜索未来 7 天内是否有财报或负面新闻，给出情绪评分 (-1 到 1)。
    Step 5: 结构优化。将建议行权日延长 14 天，行权价调整至市价 2% 以内。
    Step 6: 数学评分。确保 Risk/Reward > 2。

    请严格返回符合条件的建议（如果没有符合的则返回空数组），输出为纯 JSON 格式：
    [
      {{
        "ticker": "NVDA", 
        "side": "CALL", 
        "sentiment_score": 0.9, 
        "narrative_type": "AI服务器需求强劲", 
        "suggested_strike": 145.0, 
        "entry_stock_price": 141.2, 
        "expiration_date": "2026-02-15", 
        "risk_reward_ratio": 2.8, 
        "final_score": 9.1
      }}
    ]
    """

    try:
        response = model.generate_content(prompt)
        
        # 稳健提取 JSON
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0]
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0]
            
        final_trades = json.loads(raw_text.strip())
        
        if final_trades:
            # 数据库连接
            url = urlparse.urlparse(os.getenv("DATABASE_URL"))
            conn = psycopg2.connect(
                database=url.path[1:], user=url.username, password=url.password,
                host=url.hostname, port=url.port, sslmode='require'
            )
            cur = conn.cursor()
            
            for t in final_trades:
                # 再次确认 ticker 是否在你的原始名单内（双重保险）
                if t['ticker'] in watch_list:
                    try:
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
                        print(f"⚠️ 插入 {t['ticker']} 失败: {row_e}")
                        conn.rollback()
                        continue
                    else:
                        conn.commit()
            
            print(f"✅ 完成！已从清单中筛选并入库 {len(final_trades)} 条优质机会。")
            cur.close()
            conn.close()
        else:
            print("ℹ️ 今日清单中没有符合 6 步量化协议的交易机会。")
            
    except Exception as e:
        print(f"❌ 运行失败: {e}")

if __name__ == "__main__":
    run_targeted_scanner()