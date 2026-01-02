import os
import base64
import io
import psycopg2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image

app = FastAPI()

# 允许 Chrome 插件跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置环境
DATABASE_URL = os.getenv("DATABASE_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

@app.post("/analyze")
async def analyze_route(request: Request):
    try:
        data = await request.json()
        # 1. 解码图片
        image_bytes = base64.b64decode(data['image'].split(',')[1])
        img = Image.open(io.BytesIO(image_bytes))
        
        # 2. 调用 Gemini 多模态模型
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = "分析这张截图中的股票讨论。提取 Ticker:Sentiment 格式。只返回 JSON，例如 {'AAPL': 'Bullish', 'TSLA': 'Bearish'}"
        response = model.generate_content([prompt, img])
        
        # 3. 存入 Neon 数据库
        analysis = response.text.replace("'", '"') # 简单清洗
        # ... (此处复用你之前的数据库插入代码 save_to_db)
        
        return {"status": "success", "result": analysis}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    # Cloud Run 会自动提供 PORT 环境变量
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)