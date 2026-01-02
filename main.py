import os
import base64
import io
import json
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
INTERNAL_AUTH_KEY = os.getenv("INTERNAL_AUTH_KEY")
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL_NAME = "gemini-2.5-flash"

def save_to_db(ticker, sentiment, author, post_time, reason):
    """增强版入库函数：支持发帖人和发帖时间"""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # 即使 Ticker 相同，只要 Author 或 Post_Time 不同，就是新的有效记录
        sql = """
        INSERT INTO stock_trends (ticker, sentiment, author, post_time, reason, source) 
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            ticker.upper(), 
            sentiment.capitalize(), 
            author, 
            post_time, 
            reason, 
            "ChromeExtension"
        )
        
        cur.execute(sql, params)
        conn.commit()
        cur.close()
        print(f"✅ 已记录: {author} 发布的 {ticker} ({sentiment})")
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")
    finally:
        if conn:
            conn.close()

@app.post("/analyze")
async def analyze_route(request: Request):
    auth_key = request.headers.get("X-Internal-Key")
    if not INTERNAL_AUTH_KEY or auth_key != INTERNAL_AUTH_KEY:
        return {"status": "error", "message": "Unauthorized"}

    try:
        data = await request.json()
        image_bytes = base64.b64decode(data['image'].split(',')[1])
        img = Image.open(io.BytesIO(image_bytes))

        # 获取当前时间传给 AI，方便它计算“3小时前”的具体日期
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"--- 开始 AI 分析 (当前参考时间: {now_str}) ---")
        
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        prompt = f"""
        你是一个专业的社交媒体数据抓取助手。
        当前系统参考时间是: {now_str}。
        
        任务：分析这张 Reddit 或小红书的截图，提取以下信息：
        1. 提及的股票代码 (ticker)
        2. 情绪 (sentiment: Bullish/Bearish/Neutral)
        3. 发帖人用户名 (author: 如果找不到则填 Unknown)
        4. 原始发帖时间 (post_time: 如果是'2h ago'请计算出具体时间，格式 YYYY-MM-DD HH:MM:SS)
        
        请严格返回 JSON 数组，例如:
        [
          {{"ticker": "NVDA", "sentiment": "Bullish", "author": "UserA", "post_time": "2026-01-01 18:00:00"}},
          {{"ticker": "AAPL", "sentiment": "Bearish", "author": "UserB", "post_time": "2026-01-01 17:30:00"}}
        ]
        不要返回任何 Markdown 标记。
        """
        
        response = model.generate_content([prompt, img])
        raw_text = response.text.strip().replace("```json", "").replace("```", "")
        analysis_results = json.loads(raw_text)

        # 遍历结果并入库
        for item in analysis_results:
            save_to_db(
                ticker=item.get('ticker'),
                sentiment=item.get('sentiment'),
                author=item.get('author', 'Unknown'),
                post_time=item.get('post_time', now_str), # 默认使用当前时间
                reason="AI Vision Extraction"
            )
        
        return {"status": "success", "count": len(analysis_results), "data": analysis_results}

    except Exception as e:
        print(f"🚨 运行异常: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)