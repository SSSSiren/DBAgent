"""
FastAPI 应用入口

参考 DBAgent 的 app/main.py

启动方式：
    python -m app.main
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.schemas import HealthResponse
from app.config import get_settings
from app.memory import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    settings = get_settings()
    print(f"[DBAgent] Starting on {settings.host}:{settings.port}")
    print(f"[DBAgent] LLM: {settings.llm_model} @ {settings.llm_base_url}")
    print(f"[DBAgent] OneDBA: {settings.onedba_base_url}")
    print(f"[DBAgent] KB: {'enabled' if settings.kb_enabled else 'disabled'} (provider=openviking, url={settings.kb_openviking_url}, auto_commit={settings.kb_auto_commit_turns}turns)")
    print(f"[DBAgent] Storage backend: {settings.storage_backend}")
    print(f"[DBAgent] Preference: {'enabled' if settings.preference_enabled else 'disabled'}")
    print(f"[DBAgent] HDC: {'enabled' if settings.hdc_enabled else 'disabled'}" + (f" (auto_generate)" if settings.hdc_auto_generate else ""))
    print(f"[DBAgent] SQL Memory: {'enabled' if settings.sql_memory_enabled else 'disabled'}" + (f" (top_k={settings.sql_memory_top_k}, scope={settings.sql_memory_scope}, ttl={settings.sql_memory_ttl_days}d)" if settings.sql_memory_enabled else ""))
    print(f"[DBAgent] Admin API: {'configured' if settings.admin_api_token else 'disabled (token not set)'}")

    # 初始化存储（会话 + 偏好，创建数据库表和索引）
    storage = get_storage()
    await storage.initialize()

    yield

    # 关闭时
    print("[DBAgent] Shutting down")
    await storage.close()
    from app.client.onedba import get_onedba_client
    await get_onedba_client().close()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    settings = get_settings()

    app = FastAPI(
        title="DBAgent",
        description="基于 OpenAI 兼容 API 的 ReAct NL2SQL 智能数据库助手",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载静态文件
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 挂载路由
    app.include_router(router, prefix="/api")

    # 健康检查
    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="ok",
            engine="openai-fallback",
        )

    # 首页
    @app.get("/")
    async def index():
        index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return HTMLResponse("<h1>DBAgent</h1><p>静态文件未找到，请检查 app/static/ 目录。</p>")

    return app


# 模块级应用实例（供 uvicorn/gunicorn 使用）
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
