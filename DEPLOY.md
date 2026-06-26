# DBAgent 部署指南

## 方式一：Docker Compose（推荐）

### 1. 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入实际的 API Key：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
ONEDBA_ACCESS_TOKEN=your_onedba_token
```

### 2. 启动服务

```bash
# 构建并启动（后台运行）
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务启动后访问 `http://localhost:8000`

### 3. 更新部署

```bash
git pull
docker-compose up -d --build
```

---

## 方式二：直接 Docker 构建

```bash
# 构建镜像
docker build -t dbagent:latest .

# 运行容器
docker run -d \
  --name dbagent \
  -p 8000:8000 \
  -e DEEPSEEK_API_KEY=sk-xxxxxxxx \
  -e ONEDBA_ACCESS_TOKEN=your_token \
  -v $(pwd)/data:/app/data \
  dbagent:latest
```

---

## 方式三：传统部署（无 Docker）

### 前提条件

- Python 3.12+
- pip

### 步骤

```bash
# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 4. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 生产环境建议使用 gunicorn
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

---

## 验证部署

```bash
# 健康检查
curl http://localhost:8000/health

# 预期返回
{"status": "ok"}
```