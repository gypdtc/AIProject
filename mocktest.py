import os
import psycopg2
from urllib.parse import urlparse
import google.generativeai as genai

def mask_password(url):
    """简单脱敏处理，防止密码完全暴露在日志中（可选）"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.username}:****@{parsed.hostname}{parsed.path}"
    except:
        return "Invalid URL format"

def run_test():
    print("=== 开始云端环境测试 ===")

    # 1. 检查并打印数据库环境变量
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # 调试用：打印完整 URL (如果想看脱敏版，请用 mask_password(db_url))
        print(f"✅ 成功读取 DATABASE_URL: {db_url}")
    else:
        print("❌ 错误：环境变量 DATABASE_URL 为空！请检查 GitHub Secrets 和 Cloud Run 配置。")
        return

    # 2. 尝试连接数据库
    try:
        print("正在尝试连接 Neon 数据库...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # 简单查询测试
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        print(f"✅ 数据库连接成功！版本: {db_version}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")

    # 3. 检查并测试 Gemini AI
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"✅ 成功读取 GEMINI_API_KEY (前4位): {api_key[:4]}...")
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content("Hello, this is a cloud deployment test. Reply with 'Success'!")
            print(f"✅ Gemini AI 测试成功: {response.text.strip()}")
        except Exception as e:
            print(f"❌ Gemini AI 调用失败: {e}")
    else:
        print("⚠️ 警告：环境变量 GEMINI_API_KEY 为空。")

    print("=== 测试结束 ===")

if __name__ == "__main__":
    run_test()