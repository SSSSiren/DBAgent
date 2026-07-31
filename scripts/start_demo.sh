#!/usr/bin/env bash
# ============================================================================
# DBAgent Demo 启动脚本
#
# 用途：一键启动 DBAgent API 服务，自动打印模块状态横幅
# 用法：bash scripts/start_demo.sh [port]
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

PORT="${1:-8000}"

# ── 检查 .env 是否存在 ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在，请先基于 .env.example 创建 .env 文件"
    exit 1
fi

# ── 读取 .env 中的关键配置（兼容 KEY=VALUE 和 export KEY=VALUE） ─────
source_env() {
    local key=$1
    local default=$2
    local val
    val=$(grep -E "^[[:space:]]*${key}=" .env 2>/dev/null | head -1 | sed 's/^[[:space:]]*'"${key}"'=//' | sed 's/[[:space:]]*$//' | tr -d '"' | tr -d "'" || true)
    echo "${val:-$default}"
}

HDC_ENABLED=$(source_env HDC_ENABLED false)
SQL_MEMORY_ENABLED=$(source_env SQL_MEMORY_ENABLED false)
KB_ENABLED=$(source_env KB_ENABLED false)
STORAGE_BACKEND=$(source_env STORAGE_BACKEND memory)
LLM_MODEL=$(source_env LLM_MODEL unknown)
ONEDBA_ENV=$(source_env ONEDBA_ENV test)
LANGFUSE_ENABLED=$(source_env LANGFUSE_ENABLED false)
KB_OPENVIKING_URL=$(source_env KB_OPENVIKING_URL "http://localhost:1933")

# ── 颜色函数 ─────────────────────────────────────────────────────────
green()  { echo -e "\033[32m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }
red()    { echo -e "\033[31m$1\033[0m"; }
bold()   { echo -e "\033[1m$1\033[0m"; }
dash()   { echo -e "\033[2m────────────────────────────────────────────────────────────────\033[0m"; }

# ── 打印横幅 ─────────────────────────────────────────────────────────
echo ""
dash
echo ""
echo "   ██████╗ ██████╗  █████╗  ██████╗ ███████╗███╗   ██╗████████╗"
echo "   ██╔══██╗██╔══██╗██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝"
echo "   ██║  ██║██████╔╝███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   "
echo "   ██║  ██║██╔══██╗██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   "
echo "   ██████╔╝██████╔╝██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   "
echo "   ╚═════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   "
echo ""
echo "        NL2SQL 智能数据库助手 — Demo 模式"
echo ""
dash
echo ""
echo "  配置摘要（来自 .env）："
echo ""
printf "    %-28s %s\n" "$(bold 'HDC 数据底座：')"      "$([ "$HDC_ENABLED" = true ] && green '✅ 已启用' || red '❌ 未启用')"
printf "    %-28s %s\n" "$(bold 'SQL 历史记忆：')"     "$([ "$SQL_MEMORY_ENABLED" = true ] && green '✅ 已启用' || red '❌ 未启用')"
printf "    %-28s %s\n" "$(bold '对话记忆 (KB)：')"    "$([ "$KB_ENABLED" = true ] && green '✅ 已启用' || yellow '○ 未启用')"
printf "    %-28s %s\n" "$(bold '存储后端：')"          "$(bold "$STORAGE_BACKEND")"
printf "    %-28s %s\n" "$(bold 'LLM 模型：')"          "$(bold "$LLM_MODEL")"
printf "    %-28s %s\n" "$(bold 'OneDBA 环境：')"       "$(bold "$ONEDBA_ENV")"
printf "    %-28s %s\n" "$(bold 'Langfuse 可观测：')"  "$([ "$LANGFUSE_ENABLED" = true ] && green '✅ 已启用' || yellow '○ 未启用')"
echo ""
dash
echo ""

# ── 前置检查 ─────────────────────────────────────────────────────────
warnings=0

if [ "$HDC_ENABLED" = true ]; then
    echo "  ⏳ 检查 OpenViking 连通性 (${KB_ENABLED:+$KB_OPENVIKING_URL})"
fi

if [ "$SQL_MEMORY_ENABLED" = true ] && [ "$STORAGE_BACKEND" != sqlite ]; then
    echo "  $(red '⚠')  SQL Memory 已启用但 STORAGE_BACKEND 不是 sqlite，数据重启后将丢失"
    warnings=$((warnings + 1))
fi

if [ "$warnings" -gt 0 ]; then
    echo ""
fi

# ── 启动服务 ─────────────────────────────────────────────────────────
echo "  🚀 启动 DBAgent 服务 → http://0.0.0.0:${PORT}"
echo ""
echo "  📋 可用端点："
echo "     GET  /health                 健康检查"
echo "     POST /api/chat               对话接口（SSE 流式）"
echo "     POST /api/chat/json          对话接口（JSON）"
echo "     GET  /api/hdc/status/{db}    HDC 数据状态"
echo "     POST /api/hdc/generate       HDC 离线生成"
echo "     GET  /                       前端页面"
echo ""
echo "  📋 Demo curl 示例："
echo "     curl -X POST http://localhost:${PORT}/api/chat \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"message\":\"帮我查一下最近一个月的工单类型分布\",\"session_id\":\"demo\",\"schema_id\":65938636,\"database_name\":\"dw_onedba\",\"hdc_namespace\":\"recall_extra\"}'"
echo ""
dash
echo ""

export PORT
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
