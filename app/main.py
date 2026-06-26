"""
FastAPI 应用入口

职责：
1. 创建 FastAPI 应用实例
2. 配置中间件（CORS）
3. 注册 API 路由
4. 挂载静态文件
5. 定义健康检查和首页路由
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用

    Returns:
        FastAPI: 配置完成的应用实例
    """
    # 创建 FastAPI 应用，设置元信息
    app = FastAPI(
        title="DBAgent",
        description="LangGraph + FastAPI database analysis agent",
        version="0.1.0",
        debug=settings.DEBUG,
    )

    # 配置 CORS 中间件，允许跨域请求（开发环境）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有来源
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有请求头
    )

    # 注册 API 路由，统一添加 /api 前缀
    # 最终路由示例：POST /api/chat, GET /api/sessions/{session_id}
    app.include_router(router, prefix="/api")

    # 挂载静态文件目录，用于访问前端页面
    # 访问路径：/static/app.js, /static/index.html 等
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # 健康检查接口，用于监控和负载均衡器探测
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # favicon 路由，避免浏览器请求产生 404
    @app.get("/favicon.ico")
    async def favicon():
        return FileResponse("app/static/favicon.svg")

    # 首页路由，返回前端入口页面
    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse("app/static/index.html")

    return app


# 创建应用实例，供 uvicorn 或 gunicorn 使用
app = create_app()


# 直接运行时的入口（开发模式）
if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
