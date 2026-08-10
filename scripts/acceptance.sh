#!/usr/bin/env bash
# ============================================================================
# DBAgent all-in-one acceptance check
#
# Default mode runs deterministic local checks only.
# External systems (LLM/OneDBA/OpenViking) and NL2SQL evaluation are opt-in.
# Uses current Python/pytest by default to avoid network dependency resolution.
# Set ACCEPTANCE_USE_UV=1 to run through uv with requirements.txt.
#
# Usage:
#   bash scripts/acceptance.sh
#   bash scripts/acceptance.sh --with-external
#   bash scripts/acceptance.sh --with-external --with-evaluation
#   bash scripts/acceptance.sh --full-pytest
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -z "${NO_COLOR:-}" ]; then
    C_RESET=$'\033[0m'
    C_HINT=$'\033[36m'
    C_EXEC=$'\033[34m'
    C_OK=$'\033[32m'
    C_ERR=$'\033[31m'
    C_BOLD=$'\033[1m'
else
    C_RESET=""
    C_HINT=""
    C_EXEC=""
    C_OK=""
    C_ERR=""
    C_BOLD=""
fi

box() {
    local color="$1"
    local title="$2"
    printf '%s╔════════════════════════════════════════════════════════════════════╗%s\n' "$color" "$C_RESET"
    printf '%s║ %s%-64s%s ║%s\n' "$color" "$C_BOLD" "$title" "$C_RESET$color" "$C_RESET"
    printf '%s╚════════════════════════════════════════════════════════════════════╝%s\n' "$color" "$C_RESET"
}

print_usage() {
    box "$C_HINT" "提示 / 可选参数"
    cat <<'EOF'
DBAgent 交付验收脚本

用法:
  bash scripts/acceptance.sh [选项]

默认行为:
  只执行本地确定性检查，不强制启动服务，不访问 LLM/OneDBA/OpenViking。

可选参数:
  --start-server
      验收期间临时启动本地 API 服务，并额外检查 /health、/docs、session 等接口。

  --with-external
      启用外部依赖检查，访问 .env 中配置的 OneDBA/LLM/OpenViking 链路。
      需要先准备 .env 和真实凭证。

  --with-evaluation
      启用 NL2SQL 评测 smoke。通常与 --with-external 一起使用。

  --full-pytest
      运行 pytest -m "not integration"，覆盖所有非 integration 测试。

  --pytest-args "<args>"
      自定义 pytest 参数或测试范围，会覆盖默认本地 smoke 测试范围。
      示例: --pytest-args "tests/test_admin.py tests/test_session_api.py -q"

  --output-dir <dir>
      指定验收报告和日志输出目录，默认 acceptance-output。

  -h, --help
      显示本帮助。

示例:
  bash scripts/acceptance.sh
  bash scripts/acceptance.sh --start-server
  bash scripts/acceptance.sh --with-external --with-evaluation
  bash scripts/acceptance.sh --full-pytest --output-dir acceptance-output/full
EOF
}

print_mode() {
    box "$C_HINT" "当前执行模式"
    printf '  start_server    = %s\n' "$START_SERVER"
    printf '  with_external   = %s\n' "$WITH_EXTERNAL"
    printf '  with_evaluation = %s\n' "$WITH_EVALUATION"
    printf '  output_dir      = %s\n' "$OUT_DIR"
    printf '  pytest_args     = %s\n' "$PYTEST_ARGS"
    printf '\n'
}

read_env_value() {
    local key="$1"
    python - "$key" <<'PY'
import pathlib
import sys

key = sys.argv[1]
env_path = pathlib.Path(".env")
if not env_path.exists():
    raise SystemExit(0)
for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):].strip()
    if "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() != key:
        continue
    value = value.strip().strip('"').strip("'")
    print(value)
    break
PY
}

ENV_PORT="$(read_env_value PORT)"
ENV_HOST="$(read_env_value HOST)"
ENV_ADMIN_API_TOKEN="$(read_env_value ADMIN_API_TOKEN)"
BASE_HOST="${ENV_HOST:-0.0.0.0}"
if [ "$BASE_HOST" = "0.0.0.0" ]; then
    BASE_HOST="localhost"
fi
BASE_URL="http://${BASE_HOST}:${ENV_PORT:-8000}"
WITH_EXTERNAL=false
WITH_EVALUATION=false
START_SERVER=false
PYTEST_ARGS="tests/test_admin.py tests/test_session_api.py tests/test_cancel_registry.py tests/test_store.py tests/test_storage_manager.py tests/test_preferences.py tests/test_preferences_integration.py tests/test_sql_memory_context.py tests/test_sql_memory_store.py tests/test_context.py tests/test_prompts.py tests/test_nl2sql.py tests/test_sse_integration.py tests/test_streaming_integration.py tests/datavault/test_collector.py tests/datavault/test_retriever_updater.py tests/datavault/test_hdc_integration.py"
OUT_DIR="acceptance-output"
if [ "${ACCEPTANCE_USE_UV:-0}" = "1" ] && command -v uv >/dev/null 2>&1; then
    PY_RUN="uv run --with-requirements requirements.txt python"
    PYTEST_RUN="uv run --with-requirements requirements.txt pytest"
    PY_EXECUTOR="uv run --with-requirements requirements.txt"
else
    PY_RUN="${PYTHON:-python}"
    PYTEST_RUN="${PYTEST:-pytest}"
    PY_EXECUTOR="$PY_RUN"
fi

while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-external)
            WITH_EXTERNAL=true
            shift
            ;;
        --with-evaluation)
            WITH_EVALUATION=true
            shift
            ;;
        --start-server)
            START_SERVER=true
            shift
            ;;
        --pytest-args)
            PYTEST_ARGS="${2:-}"
            shift 2
            ;;
        --full-pytest)
            PYTEST_ARGS="-m \"not integration\""
            shift
            ;;
        --output-dir)
            OUT_DIR="${2:-}"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Run 'bash scripts/acceptance.sh --help' for usage." >&2
            exit 2
            ;;
    esac
done

print_usage
echo
print_mode

mkdir -p "$OUT_DIR"
LOG_DIR="$OUT_DIR/logs"
ARTIFACT_DIR="$OUT_DIR/artifacts"
CACHE_DIR="$OUT_DIR/.uv-cache"
mkdir -p "$LOG_DIR" "$ARTIFACT_DIR" "$CACHE_DIR"
SUMMARY="$OUT_DIR/acceptance-summary.md"
LOG="$LOG_DIR/00-acceptance.log"
: > "$LOG"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
SERVER_PID=""
CHECK_INDEX=0

log() {
    printf '%s\n' "$*" | tee -a "$LOG"
}

record() {
    local name="$1"
    local result="$2"
    local notes="${3:-}"
    printf '| %s | %s | %s |\n' "$name" "$result" "$notes" >> "$SUMMARY"
    case "$result" in
        PASS) PASS_COUNT=$((PASS_COUNT + 1)) ;;
        FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
        SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
    esac
}

run_check() {
    local name="$1"
    local cmd="$2"
    CHECK_INDEX=$((CHECK_INDEX + 1))
    local safe_name
    safe_name="$(printf '%s' "$name" | tr ' /' '__')"
    local outfile
    outfile="$(printf '%s/%02d-%s.log' "$LOG_DIR" "$CHECK_INDEX" "$safe_name")"
    log "${C_EXEC}==> 执行检查: $name${C_RESET}"
    if bash -lc "$cmd" > "$outfile" 2>&1; then
        log "${C_OK}    PASS: $name${C_RESET}"
        record "$name" "PASS" "log: $outfile"
        return 0
    fi
    log "${C_ERR}    FAIL: $name${C_RESET}"
    record "$name" "FAIL" "log: $outfile"
    return 1
}

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
        wait "$SERVER_PID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
NOW="$(date '+%Y-%m-%d %H:%M:%S %z')"

cat > "$SUMMARY" <<EOF
# DBAgent 交付验收报告

- 代码版本: $GIT_SHA
- 执行时间: $NOW
- 服务地址: $BASE_URL
- 外部依赖检查: $WITH_EXTERNAL
- 评测检查: $WITH_EVALUATION
- Python 执行器: $PY_EXECUTOR
- 配置来源: ${PROJECT_DIR}/.env（存在时加载）

## 检查项

| 检查项 | 结果 | 说明 |
|---|---|---|
EOF

EXIT_CODE=0

box "$C_EXEC" "执行过程 / 本地检查"

run_check "Python 执行器可用" "test -f requirements.txt && $PY_RUN --version" || EXIT_CODE=1

run_check "Python 编译检查" "$PY_RUN -m compileall -q app tests" || EXIT_CODE=1

run_check "配置默认值检查" "$PY_RUN - <<'PY'
from app.config import Settings
s = Settings(_env_file=None)
assert s.storage_backend == 'sqlite', s.storage_backend
assert s.llm_embedding_provider == 'auto', s.llm_embedding_provider
assert s.onedba_env == 'prd', s.onedba_env
assert s.sql_memory_enabled is False, s.sql_memory_enabled
assert s.hdc_enabled is False, s.hdc_enabled
assert s.langfuse_enabled is False, s.langfuse_enabled
print('defaults ok')
PY" || EXIT_CODE=1

run_check "关键文档检查" "test -f README.md && test -f DEPLOY.md && test -f docs/api-guide.md && test -f docs/admin-api-guide.md && test -f docs/delivery-checklist.md" || EXIT_CODE=1

run_check "本地 smoke 测试" "$PYTEST_RUN -q $PYTEST_ARGS" || EXIT_CODE=1

if [ "$START_SERVER" = true ]; then
    log "${C_EXEC}==> 执行操作: 启动本地服务${C_RESET}"
    SERVER_PORT="$(BASE_URL="$BASE_URL" $PY_RUN - <<'PY'
from urllib.parse import urlparse
import os
parsed = urlparse(os.environ["BASE_URL"])
print(parsed.port or (443 if parsed.scheme == "https" else 80))
PY
)"
    $PY_RUN -m uvicorn app.main:app --host 0.0.0.0 --port "$SERVER_PORT" > "$LOG_DIR/server.log" 2>&1 &
    SERVER_PID="$!"
    sleep 3
fi

if curl -fsS "$BASE_URL/health" > "$ARTIFACT_DIR/health.json" 2> "$LOG_DIR/health.err"; then
    record "健康检查接口" "PASS" "已保存: $ARTIFACT_DIR/health.json"
else
    record "健康检查接口" "SKIP" "服务不可达；可使用 --start-server 启动本地服务"
fi

if curl -fsS -o /dev/null "$BASE_URL/docs" 2> "$LOG_DIR/docs.err"; then
    record "OpenAPI 页面" "PASS" "$BASE_URL/docs"
else
    record "OpenAPI 页面" "SKIP" "服务不可达"
fi

if [ -n "$ENV_ADMIN_API_TOKEN" ] && curl -fsS "$BASE_URL/api/admin/overview" -H "Authorization: Bearer $ENV_ADMIN_API_TOKEN" > "$ARTIFACT_DIR/admin-overview.json" 2> "$LOG_DIR/admin-overview.err"; then
    record "Admin 认证接口" "PASS" "已保存: $ARTIFACT_DIR/admin-overview.json"
else
    record "Admin 认证接口" "SKIP" "需要运行中的服务和 .env 中的 ADMIN_API_TOKEN"
fi

if curl -fsS -X POST "$BASE_URL/api/sessions" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"acceptance"}' > "$ARTIFACT_DIR/session-create.json" 2> "$LOG_DIR/session-create.err"; then
    record "会话接口" "PASS" "已保存: $ARTIFACT_DIR/session-create.json"
else
    record "会话接口" "SKIP" "服务不可达"
fi

if [ "$WITH_EXTERNAL" = true ]; then
    if [ ! -f ".env" ]; then
        record "外部依赖配置" "FAIL" "缺少 .env；请先执行 cp .env.example .env 并填入真实配置"
        EXIT_CODE=1
    else
        record "外部依赖配置" "PASS" ".env 已存在"
    fi

    run_check "OneDBA 平台连通" "$PY_RUN - <<'PY'
import asyncio
from app.client.onedba import get_onedba_client
from app.config import get_settings

async def main():
    settings = get_settings()
    client = get_onedba_client()
    try:
        databases = await client.list_databases(env_type=settings.onedba_env, page=1, size=1)
        sample = databases[0] if databases else {}
        result = {
            'mode': 'platform_auth_list_databases',
            'env': settings.onedba_env,
            'returnedDatabaseCount': len(databases),
            'note': '列表为空不代表平台/token 不可用，可能是当前用户无可列出库或默认筛选无命中',
        }
        if sample:
            result.update({
                'sampleSchemaId': sample.get('schemaId'),
                'sampleSchemaName': sample.get('schemaName'),
                'sampleInstanceName': sample.get('instanceName'),
            })
        print(result)
    finally:
        await client.close()

asyncio.run(main())
PY" || EXIT_CODE=1

    run_check "外部依赖对话接口" "curl -fsS -X POST '$BASE_URL/api/chat/sync' -H 'Content-Type: application/json' -d '{\"user_id\":\"acceptance\",\"session_id\":\"acceptance-sync\",\"message\":\"列出我可以查询的数据库\"}'" || EXIT_CODE=1

    HDC_ENABLED_ACTUAL="$($PY_RUN - <<'PY'
from app.config import get_settings
print("true" if get_settings().hdc_enabled else "false")
PY
)"
    if [ "$HDC_ENABLED_ACTUAL" = "true" ]; then
        run_check "HDC 状态接口" "$PY_RUN - <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = '$BASE_URL/api/hdc/status/dw_onedba?schema_id=65938636'
out_path = '$ARTIFACT_DIR/hdc-status.json'

try:
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read().decode('utf-8')
except urllib.error.HTTPError as exc:
    body = exc.read().decode('utf-8', errors='replace')
    raise SystemExit(f'HDC 状态接口 HTTP {exc.code}: {body}')
except Exception as exc:
    raise SystemExit(f'HDC 状态接口请求失败: {exc}')

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(body)

try:
    data = json.loads(body)
except json.JSONDecodeError as exc:
    raise SystemExit(f'HDC 状态接口返回非 JSON: {exc}: {body[:500]}')

if data.get('error'):
    raise SystemExit(f'HDC 状态接口返回 error: {data.get(\"error\")}')
if data.get('exists') is not True:
    raise SystemExit(f'HDC 数据不存在或 OpenViking 不可用: {data}')
if int(data.get('namespace_count') or 0) <= 0 and not data.get('namespace'):
    raise SystemExit(f'HDC namespace_count 为 0: {data}')

print(f'HDC 状态正常，响应已保存: {out_path}')
PY" || EXIT_CODE=1
    else
        record "HDC 状态接口" "SKIP" "应用配置 HDC_ENABLED 不是 true"
    fi
else
    record "OneDBA 平台连通" "SKIP" "使用 --with-external 启用"
    record "外部依赖对话接口" "SKIP" "使用 --with-external 启用"
    record "HDC 状态接口" "SKIP" "使用 --with-external 且 HDC_ENABLED=true 启用"
fi

if [ "$WITH_EVALUATION" = true ]; then
    EVALUATION_HDC_ARGS="$($PY_RUN - <<'PY'
from app.config import get_settings
print("--with-hdc --verbose-hdc" if get_settings().hdc_enabled else "")
PY
)"
    run_check "评测 smoke" "$PY_RUN -m tests.evaluation.cli run --ids TC-001 --no-llm-judge --no-quality-judge $EVALUATION_HDC_ARGS" || EXIT_CODE=1
else
    record "评测 smoke" "SKIP" "使用 --with-evaluation 启用"
fi

{
    echo
    echo "## 汇总"
    echo
    echo "- PASS: $PASS_COUNT"
    echo "- FAIL: $FAIL_COUNT"
    echo "- SKIP: $SKIP_COUNT"
    if [ "$FAIL_COUNT" -eq 0 ]; then
        echo "- 最终结果: PASS"
    else
        echo "- 最终结果: FAIL"
    fi
} >> "$SUMMARY"

log ""
log "验收报告: $SUMMARY"
log "PASS=$PASS_COUNT FAIL=$FAIL_COUNT SKIP=$SKIP_COUNT"

if [ "$FAIL_COUNT" -ne 0 ]; then
    exit 1
fi
exit "$EXIT_CODE"
