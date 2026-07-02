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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    settings = get_settings()
    print(f"[SDK-DBAgent] Starting on {settings.host}:{settings.port}")
    print(f"[SDK-DBAgent] LLM: {settings.llm_model} @ {settings.llm_base_url}")
    print(f"[SDK-DBAgent] OneDBA: {settings.onedba_base_url}")

    yield

    # 关闭时
    print("[SDK-DBAgent] Shutting down")
    from app.client.onedba import get_onedba_client
    await get_onedba_client().close()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    settings = get_settings()

    app = FastAPI(
        title="SDK-DBAgent",
        description="基于 claude-agent-sdk 的 NL2SQL 智能数据库助手",
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
        from app.agent.runner import _is_sdk_available
        return HealthResponse(
            status="ok",
            sdk_available=_is_sdk_available(),
        )

    # 首页
    @app.get("/")
    async def index():
        index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return HTMLResponse("<h1>SDK-DBAgent</h1><p>静态文件未找到，请检查 app/static/ 目录。</p>")

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
