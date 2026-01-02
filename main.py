import os
import base64
import io
import json
import psycopg2
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

# 配置环境
DATABASE_URL = os.getenv("DATABASE_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def save_to_db(ticker, sentiment, reason):
    """实际执行数据库插入的函数"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO stock_trends (ticker, sentiment, reason, source) VALUES (%s, %s, %s, %s)",
            (ticker, sentiment, reason, "ChromeExtension")
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 已存入数据库: {ticker}")
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")

@app.post("/analyze")
async def analyze_route(request: Request):
    try:
        data = await request.json()
        # 1. 解码图片
        image_bytes = base64.b64decode(data['image'].split(',')[1])
        img = Image.open(io.BytesIO(image_bytes))
        
        # 2. 调用 Gemini 多模态模型 (修正版本号为 2.5-flash)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = """
        分析这张截图中的股票讨论。
        请仅返回一个 JSON 对象，格式如下：
        {"AAPL": "Bullish", "TSLA": "Bearish"}
        如果没有发现股票，返回空对象 {}。不要包含任何 markdown 格式代码块。
        """
        response = model.generate_content([prompt, img])
        
        # 3. 解析并存入数据库
        # 清洗可能存在的 markdown 代码块标记 ```json ... ```
        raw_text = response.text.strip().replace("```json", "").replace("```", "")
        analysis_results = json.loads(raw_text)
        
        for ticker, sentiment in analysis_results.items():
            # 这里 reason 暂时传空，或者你可以让 Gemini 多写点理由
            save_to_db(ticker, sentiment, "Analyzed from screenshot")
        
        return {"status": "success", "result": analysis_results}
    except Exception as e:
        print(f"运行时出错: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)