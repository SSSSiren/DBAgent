"""DBAgent gunicorn 生产配置。

启动：gunicorn app.main:app -c gunicorn_conf.py

设计要点：
- UvicornWorker：保留 uvicorn 的 ASGI + lifespan + WebSocket 支持（DBAgent 的 SSE/WS 端点依赖 ASGI 生命周期）。
- workers：默认按 (2*CPU+1) 计算，上限 8，可经 WEB_CONCURRENCY 环境变量覆盖。
- worker_class 用 uvicorn 的 gunicorn 集成，而非纯异步 worker（保证 SSE 流式响应正确）。
- graceful_timeout / timeout：留足 LLM 长推理时间（ReAct 循环单轮可能 >30s）。
- preload_app：True，共享代码减少内存占用；lifespan 仍由各 worker 独立执行（StorageManager 初始化在每个 worker）。
"""

import os

# 等待 worker 处理完进行中的请求再关闭，避免 SSE 流被切断
graceful_timeout = 30
# 单请求超时：LLM ReAct 多轮推理耗时较高，放宽到 120s
timeout = 120
# 保持 worker 活性，避免长连接 idle 被杀
keepalive = 5
# 监听
bind = "0.0.0.0:8000"
# 预加载应用（共享 import，节省内存；lifespan 仍在各 worker 启动）
preload_app = True
# 日志
accesslog = "-"
errorlog = "-"
loglevel = "info"
# 优雅关闭
worker_exit_timeout = 30


def _resolve_workers() -> int:
    """按 (2*CPU+1) 计算 worker 数，上限 8；允许 WEB_CONCURRENCY 覆盖。"""
    env = os.environ.get("WEB_CONCURRENCY")
    if env and env.strip().isdigit():
        return max(1, min(8, int(env)))
    try:
        cpu = os.cpu_count() or 1
    except NotImplementedError:
        cpu = 1
    return max(1, min(8, 2 * cpu + 1))


workers = _resolve_workers()
# 使用 uvicorn 的 gunicorn worker 集成，保留 ASGI/lifespan/WebSocket
worker_class = "uvicorn.workers.UvicornWorker"
