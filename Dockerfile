# DBAgent Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r requirements.txt

# 复制代码
COPY app/ ./app/
COPY gunicorn_conf.py ./
COPY data/ ./data/

# 创建数据目录
RUN mkdir -p /app/data/user_semantic_rules

# 暴露端口
EXPOSE 8000

# 启动命令：gunicorn 多 worker 生产部署
# - UvicornWorker 保留 ASGI lifespan（StorageManager 初始化）与 SSE/WS 支持
# - worker 数由 gunicorn_conf.py 按 CPU 自动计算，可经 WEB_CONCURRENCY 覆盖
CMD ["gunicorn", "app.main:app", "-c", "gunicorn_conf.py"]