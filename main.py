import os
import base64
import io
import json
import psycopg2
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image

app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 配置区 ---
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# 设置一个只有你插件知道的密钥
INTERNAL_AUTH_KEY = os.getenv("INTERNAL_AUTH_KEY")

genai.configure(api_key=GEMINI_API_KEY)
# 使用 2.0 版本
GEMINI_MODEL_NAME = "gemini-2.5-flash" 

def save_to_db(ticker, sentiment, reason):
    """将结果持久化到 Neon 数据库，带有详细日志"""
    conn = None
    try:
        print(f"尝试连接数据库...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        sql = "INSERT INTO stock_trends (ticker, sentiment, reason, source) VALUES (%s, %s, %s, %s)"
        params = (ticker.upper(), sentiment.capitalize(), reason, "ChromeExtension")
        
        print(f"正在执行 SQL: {sql} 参数: {params}")
        cur.execute(sql, params)
        
        conn.commit()
        cur.close()
        print(f"✅ 数据库写入成功: {ticker}")
    except Exception as e:
        print(f"❌ 数据库写入过程中出错: {str(e)}")
        # 抛出异常以便在外层捕获
        raise e
    finally:
        if conn:
            conn.close()

@app.post("/analyze")
async def analyze_route(request: Request):
    # 安全校验：检查 Header 是否包含正确的 Key
    auth_key = request.headers.get("X-Internal-Key")
    print(f"收到请求，校验 Key...")
    
    if auth_key != INTERNAL_AUTH_KEY:
        print(f"⚠️ 未授权的访问尝试！Key 不匹配。")
        return {"status": "error", "message": "Unauthorized"}

    try:
        print("1. 正在解析请求 JSON...")
        data = await request.json()
        image_data = data.get('image')
        
        if not image_data:
            print("❌ 请求中没有图片数据")
            return {"status": "error", "message": "No image"}

        print("2. 正在解码 Base64 图片...")
        image_bytes = base64.b64decode(image_data.split(',')[1])
        img = Image.open(io.BytesIO(image_bytes))
        print(f"📷 图片加载成功，尺寸: {img.size}")
        
        print(f"3. 正在调用 AI 模型 ({GEMINI_MODEL_NAME})...")
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        prompt = """
        分析这张截图中的股票讨论。
        提取股票代码和情绪（Bullish/Bearish/Neutral）。
        严格以 JSON 格式返回，例如: {"AAPL": "Bullish"}
        不要包含 ```json 等标记，只要纯 JSON 文本。
        """
        
        response = model.generate_content([prompt, img])
        print(f"🤖 AI 原始返回内容: {response.text}")
        
        # 清洗并解析 JSON
        raw_text = response.text.strip().replace("```json", "").replace("```", "")
        analysis_results = json.loads(raw_text)
        print(f"📦 解析后的 JSON: {analysis_results}")
        
        if not analysis_results:
            print("📝 AI 未在图中发现股票信息")
            return {"status": "success", "result": {}, "message": "No stocks found"}

        # 存入数据库
        for ticker, sentiment in analysis_results.items():
            save_to_db(ticker, sentiment, "AI vision analysis")
        
        return {"status": "success", "result": analysis_results}

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"🚨 运行异常详情:\n{error_detail}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)