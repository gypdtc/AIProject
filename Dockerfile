# 使用轻量级 Python 镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（psycopg2 需要一些编译工具）
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有代码到镜像中
COPY . .

# 修改运行命令：运行 Python 后睡眠 60 秒，防止 Cloud Run 立即判定为失败
CMD python mocktest.py && sleep 60