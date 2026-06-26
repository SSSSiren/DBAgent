# DBAgent Dockerfile
# 多阶段构建，减小镜像体积

# ========== 构建阶段 ==========
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ========== 运行阶段 ==========
FROM python:3.12-slim AS runtime

WORKDIR /app

# 从构建阶段复制 pip 包
COPY --from=builder /root/.local /root/.local

# 确保 pip 包在 PATH 中
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# 只复制运行时需要的代码
COPY app/ ./app/
COPY data/ ./data/

# 创建数据目录（用于持久化）
RUN mkdir -p /app/data/vector_store /app/data/user_semantic_rules

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]