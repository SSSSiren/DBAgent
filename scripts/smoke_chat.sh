#!/usr/bin/env bash
# ============================================================================
# DBAgent 对话冒烟脚本
#
# 用途：提供可直接运行的 curl 请求，检查 HDC + SQL Memory 对话链路
# 用法：bash scripts/smoke_chat.sh [port]
# ============================================================================
set -euo pipefail

PORT="${1:-8000}"
BASE="http://localhost:${PORT}"

red()    { echo -e "\033[31m$1\033[0m"; }
green()  { echo -e "\033[32m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }
bold()   { echo -e "\033[1m$1\033[0m"; }
dash()   { echo -e "\033[2m────────────────────────────────────────────────────────────────\033[0m"; }

# ── 检查服务存活 ─────────────────────────────────────────────────────
echo ""
echo "  ⏳ 检查服务连通性..."
if ! curl -s -o /dev/null -w "%{http_code}" "${BASE}/health" 2>/dev/null | grep -q 200; then
    echo "  $(red '❌') 服务未启动，请先运行: bash scripts/start.sh"
    echo ""
    exit 1
fi
echo "  $(green '✅') DBAgent 服务运行中"
echo ""

# ── 场景选择菜单 ────────────────────────────────────────────────────
echo "  请选择检查场景："
echo ""
echo "  $(bold '1)') 基础 NL2SQL — 单表查询"
echo "     工单系统的数据导出类工单"
echo ""
echo "  $(bold '2)') 聚合查询 — GROUP BY + 排序"
echo "     各状态工单的数量分布"
echo ""
echo "  $(bold '3)') 多表 JOIN — 跨表关联"
echo "     工单与审计记录关联查询"
echo ""
echo "  $(bold '4)') 时间窗口 — 趋势分析"
echo "     按天统计告警趋势"
echo ""
echo "  $(bold '5)') 自定义提问"
echo ""
echo "  $(bold 'q)') 退出"
echo ""

read -r -p "  请输入选择 [1-5/q]: " choice
echo ""

case "$choice" in
    1)
        QUESTION="查询order_type='dataExport'的工单，返回工单ID、提交人、状态和创建时间"
        ;;
    2)
        QUESTION="统计每种工单状态的数量，按数量降序排列"
        ;;
    3)
        QUESTION="查询工单及其审计记录，返回工单ID、工单类型、SQL类型、风险等级"
        ;;
    4)
        QUESTION="统计2024年7月每天的告警数量，按日期升序排列"
        ;;
    5)
        read -r -p "  请输入你的问题: " QUESTION
        ;;
    q|Q)
        echo "  退出"
        exit 0
        ;;
    *)
        echo "  $(red '无效选择')"
        exit 1
        ;;
esac

echo ""
dash
echo ""
echo "  📤 发送请求（SSE 流式响应）："
echo ""
echo "  $(bold '问题：') ${QUESTION}"
echo ""

# ── 发送 SSE 请求 ───────────────────────────────────────────────────
curl -N -X POST "${BASE}/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
        \"message\": \"${QUESTION}\",
        \"session_id\": \"smoke-$(date +%s)\",
        \"schema_id\": 65938636,
        \"database_name\": \"dw_onedba\",
        \"hdc_namespace\": \"recall_extra\"
    }" 2>/dev/null | while IFS= read -r line; do
    # 给 SSE 事件加上颜色标记
    if [[ "$line" == event:* ]]; then
        echo ""
        echo -e "\033[36m${line}\033[0m"
    elif [[ "$line" == data:* ]]; then
        # 截断过长的 data 行
        if [ ${#line} -gt 200 ]; then
            echo "${line:0:200}..."
        else
            echo "$line"
        fi
    elif [[ "$line" == "" ]]; then
        :
    else
        echo "$line"
    fi
done

echo ""
dash
echo ""
echo "  $(green '✅') 请求完成"
echo ""
echo "  💡 提示："
echo "     - 如果 HDC 已启用，查询时 Agent 上下文会注入 [数据底座] 知识"
echo "     - 如果 SQL Memory 已启用，重复执行相同场景的问题会触发记忆检索"
echo "     - 可以用 Python 脚本查看 SQL Memory 积累的记忆："
echo "       python tools/sql_memory_admin.py stats --mine"
echo ""
