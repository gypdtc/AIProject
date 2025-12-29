import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 测试列出所有可用模型
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"可用模型: {m}")

# 测试运行
model = genai.GenerativeModel('gemini-2.0-flash-thinking-exp-01-21')
response = model.generate_content("Hi")
print(f"测试响应: {response.text}")
