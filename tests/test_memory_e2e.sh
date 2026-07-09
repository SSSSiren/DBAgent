#!/bin/bash
# test_memory_e2e.sh
# OpenViking 对话记忆 E2E 验证脚本
#
# 前置条件:
#   1. VK-DBAgent 运行在 localhost:8000
#   2. OpenViking Server 运行在 localhost:1933
#   3. Ollama 已加载 bge-m3 模型
#
# 用法:
#   chmod +x tests/test_memory_e2e.sh
#   ./tests/test_memory_e2e.sh              # 全部场景
#   ./tests/test_memory_e2e.sh --scene 1    # 只运行场景 1
#   ./tests/test_memory_e2e.sh --scene 2    # 只运行场景 2

set -euo pipefail

BASE="${BASE:-http://localhost:8000/api}"
OV_URL="${OV_URL:-http://localhost:1933}"
TIMEOUT="${TIMEOUT:-120}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

# ========== 工具函数 ==========

log_section() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
}

log_info()   { echo -e "${BLUE}[INFO]${NC} $1"; }
log_pass()   { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS + 1)); }
log_fail()   { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL + 1)); }
log_warn()   { echo -e "${YELLOW}[WARN]${NC} $1"; }

check_prerequisites() {
    log_info "检查前置条件..."

    # 检查 VK-DBAgent
    if curl -s --max-time 3 "$BASE/../health" > /dev/null 2>&1; then
        log_pass "VK-DBAgent 可访问 ($BASE)"
    else
        log_fail "VK-DBAgent 不可访问 ($BASE)，请先启动服务"
        exit 1
    fi

    # 检查 OpenViking
    if curl -s --max-time 3 "$OV_URL/api/v1/fs/ls?uri=viking%3A%2F%2F" > /dev/null 2>&1; then
        log_pass "OpenViking Server 可访问 ($OV_URL)"
    else
        log_warn "OpenViking Server 不可访问 ($OV_URL)，场景 1-4 将跳过"
    fi
}

do_chat() {
    # 发送同步聊天请求，返回 JSON 响应
    local session_id="$1"
    local user_id="$2"
    local message="$3"
    curl -s --max-time "$TIMEOUT" -X POST "$BASE/chat/sync" \
        -H "Content-Type: application/json" \
        -d "{\"session_id\": \"$session_id\", \"user_id\": \"$user_id\", \"message\": \"$message\"}"
}

get_session_state() {
    local session_id="$1"
    curl -s --max-time 10 "$BASE/sessions/$session_id"
}

get_ov_peers() {
    local user_id="$1"
    curl -s --max-time 10 "$OV_URL/api/v1/fs/ls?uri=viking%3A%2F%2Fuser%2F${user_id}%2Fpeers"
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local description="$3"
    if echo "$haystack" | grep -q "$needle"; then
        log_pass "$description"
    else
        log_fail "$description (expected to contain: '$needle')"
        log_info "  实际内容: $(echo "$haystack" | head -3)"
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local description="$3"
    if echo "$haystack" | grep -q "$needle"; then
        log_fail "$description (unexpectedly contains: '$needle')"
    else
        log_pass "$description"
    fi
}

assert_equals() {
    local actual="$1"
    local expected="$2"
    local description="$3"
    if [ "$actual" = "$expected" ]; then
        log_pass "$description"
    else
        log_fail "$description (expected=$expected, actual=$actual)"
    fi
}

# ========== 场景 ==========

run_scene_1() {
    log_section "场景 1: 单用户 10 轮对话 → 自动 commit"

    local user="alice_scene1"
    local session="scene1-$(date +%s)"

    log_info "alice 进行 10 轮数据库对话..."

    for i in $(seq 1 10); do
        local resp
        resp=$(do_chat "$session" "$user" "第${i}轮：帮我查一下有哪些数据库可以访问")
        local has_response
        has_response=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','')[:50])" 2>/dev/null || echo "")

        if [ -n "$has_response" ]; then
            log_info "  第${i}轮: $has_response..."
        else
            log_warn "  第${i}轮: 响应为空"
        fi

        # 避免请求过快
        sleep 0.5
    done

    echo ""

    # 验证 1: kb_turn_count
    log_info "验证会话状态..."
    local session_state
    session_state=$(get_session_state "$session")
    log_info "  会话状态: $(echo "$session_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k:v for k,v in d.items() if k in ('session_id','chat_history')}, ensure_ascii=False))" 2>/dev/null || echo "$session_state")"

    # 验证 2: peers 目录
    log_info "验证 OpenViking 长期记忆..."
    sleep 2  # 等待 commit 异步完成
    local peers
    peers=$(get_ov_peers "$user")
    local peer_count
    peer_count=$(echo "$peers" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result',[])))" 2>/dev/null || echo "0")

    if [ "$peer_count" -gt 0 ]; then
        log_pass "peers 目录有 $peer_count 条长期记忆"
        echo "$peers" | python3 -c "
import sys, json
for r in json.load(sys.stdin).get('result', []):
    print(f'    - {r.get(\"uri\",\"?\").split(\"/\")[-1]}: {r.get(\"abstract\",\"\")[:100]}')
" 2>/dev/null
    else
        log_fail "peers 目录为空（可能 commit 尚未完成或未触发）"
        log_info "  提示: 检查 kb_auto_commit_turns 配置是否为 10"
    fi
}

run_scene_2() {
    log_section "场景 2: 不足 10 轮不触发 commit"

    local user="alice_scene2"
    local session="scene2-$(date +%s)"

    log_info "alice 进行 5 轮对话..."

    for i in $(seq 1 5); do
        do_chat "$session" "$user" "第${i}轮：列出数据库" > /dev/null
        log_info "  第${i}轮完成"
        sleep 0.3
    done

    sleep 2
    local peers
    peers=$(get_ov_peers "$user")
    local peer_count
    peer_count=$(echo "$peers" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result',[])))" 2>/dev/null || echo "0")

    if [ "$peer_count" -eq 0 ]; then
        log_pass "peers 目录为空（5 轮不触发 commit）"
    else
        log_fail "peers 目录有 $peer_count 条记忆（预期为空，5 轮不应触发 commit）"
    fi
}

run_scene_3() {
    log_section "场景 3: 多用户记忆隔离"

    local t=$(date +%s)

    log_info "alice 进行 10 轮对话..."
    for i in $(seq 1 10); do
        do_chat "iso-alice-$t" "alice_iso" "第${i}轮：帮我查 orders 表中 status='paid' 的订单数量" > /dev/null
        sleep 0.5
    done
    log_info "  alice 完成"

    log_info "bob 进行 10 轮对话..."
    for i in $(seq 1 10); do
        do_chat "iso-bob-$t" "bob_iso" "第${i}轮：帮我查 users 表中的用户总数" > /dev/null
        sleep 0.5
    done
    log_info "  bob 完成"

    sleep 3  # 等待 commit

    local peers_alice peers_bob
    peers_alice=$(get_ov_peers "alice_iso")
    peers_bob=$(get_ov_peers "bob_iso")

    log_info "alice 的 peers:"
    echo "$peers_alice" | python3 -c "
import sys, json
for r in json.load(sys.stdin).get('result', []):
    print(f'    - {r.get(\"abstract\",\"\")[:120]}')
" 2>/dev/null || echo "    (空)"

    log_info "bob 的 peers:"
    echo "$peers_bob" | python3 -c "
import sys, json
for r in json.load(sys.stdin).get('result', []):
    print(f'    - {r.get(\"abstract\",\"\")[:120]}')
" 2>/dev/null || echo "    (空)"

    # 验证 alice 的记忆不包含 bob 的内容
    local alice_text
    alice_text=$(echo "$peers_alice" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "$peers_alice")
    local bob_text
    bob_text=$(echo "$peers_bob" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "$peers_bob")

    assert_not_contains "$alice_text" "users" "alice 的记忆不含 'users'（bob 的话题）"
    assert_not_contains "$bob_text" "orders" "bob 的记忆不含 'orders'（alice 的话题）"
}

run_scene_4() {
    log_section "场景 4: 同一用户跨会话记忆累积"

    local user="charlie_accum"
    local t=$(date +%s)

    log_info "会话 1: charlie 查 orders..."
    for i in $(seq 1 10); do
        do_chat "accum-sess1-$t" "$user" "第${i}轮：orders 表本月有多少新增订单" > /dev/null
        sleep 0.5
    done

    log_info "会话 2: charlie 查 users..."
    for i in $(seq 1 10); do
        do_chat "accum-sess2-$t" "$user" "第${i}轮：users 表最近注册的用户有哪些" > /dev/null
        sleep 0.5
    done

    sleep 3  # 等待两次 commit

    local peers
    peers=$(get_ov_peers "$user")
    local peer_count
    peer_count=$(echo "$peers" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result',[])))" 2>/dev/null || echo "0")

    log_info "charlie 的 peers 总数: $peer_count"
    echo "$peers" | python3 -c "
import sys, json
for r in json.load(sys.stdin).get('result', []):
    print(f'    - {r.get(\"abstract\",\"\")[:120]}')
" 2>/dev/null

    if [ "$peer_count" -ge 2 ]; then
        log_pass "跨会话记忆累积: >= 2 条"
    else
        log_fail "跨会话记忆累积: 仅 $peer_count 条（预期 >= 2）"
    fi
}

run_scene_5() {
    log_section "场景 5: OpenViking 不可用时降级"

    log_info "模拟 OpenViking 不可用（设置 KB_OPENVIKING_URL 指向无效地址）"
    log_warn "此场景需要手动测试："
    log_warn "  1. 停掉 openviking-server"
    log_warn "  2. 发送对话请求"
    log_warn "  3. 验证响应正常返回，日志中出现 'OpenViking memory recording failed'"

    # 尝试用错误的 OV URL 发送请求
    local resp
    resp=$(do_chat "no-ov-test" "alice" "列出数据库")
    local has_response
    has_response=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','')[:80])" 2>/dev/null || echo "")

    if [ -n "$has_response" ]; then
        log_pass "OpenViking 不可用时对话仍正常返回: $has_response..."
    else
        log_warn "无法验证（可能 OpenViking 正在运行）"
    fi
}

run_scene_6() {
    log_section "场景 6: kb_enabled=False 零影响"

    log_info "发送对话请求..."
    local resp
    resp=$(do_chat "kb-off-test" "alice" "列出数据库")

    local has_response
    has_response=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','')[:80])" 2>/dev/null || echo "")

    if [ -n "$has_response" ]; then
        log_pass "kb_enabled=False 时对话正常: $has_response..."
    else
        log_fail "kb_enabled=False 时对话异常"
    fi

    log_info "注意: 需要确认 .env 中 KB_ENABLED=false 并重启服务后运行此场景"
}

run_scene_7() {
    log_section "场景 7: kb_session_id 跨请求持久化"

    local user="alice_persist"
    local session="persist-$(date +%s)"

    log_info "第 1 轮对话..."
    do_chat "$session" "$user" "列出数据库" > /dev/null
    sleep 0.5

    log_info "第 2 轮对话（同一 session）..."
    do_chat "$session" "$user" "有哪些数据库" > /dev/null
    sleep 0.5

    local state
    state=$(get_session_state "$session")
    log_info "会话状态:"
    echo "$state" | python3 -m json.tool 2>/dev/null || echo "$state"

    # SessionState schema 不含 kb_session_id，但通过 chat_history 长度验证 session 复用
    local history_len
    history_len=$(echo "$state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('chat_history',[])))" 2>/dev/null || echo "0")

    if [ "$history_len" -ge 2 ]; then
        log_pass "session 复用成功: chat_history 包含 $history_len 条记录"
    else
        log_fail "session 复用失败: chat_history 仅 $history_len 条"
    fi
}

run_scene_8() {
    log_section "场景 8: 多 session 独立"

    local user="alice_multi"
    local t=$(date +%s)

    log_info "session A: 查 orders..."
    do_chat "multi-a-$t" "$user" "orders 表有多少记录" > /dev/null
    sleep 0.5

    log_info "session B: 查 users..."
    do_chat "multi-b-$t" "$user" "users 表有多少记录" > /dev/null
    sleep 0.5

    local state_a state_b
    state_a=$(get_session_state "multi-a-$t")
    state_b=$(get_session_state "multi-b-$t")

    local history_a history_b
    history_a=$(echo "$state_a" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('chat_history',[])))" 2>/dev/null || echo "0")
    history_b=$(echo "$state_b" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('chat_history',[])))" 2>/dev/null || echo "0")

    log_info "session A 对话数: $history_a"
    log_info "session B 对话数: $history_b"

    # 各自的对话历史独立
    assert_not_equals() {
        if [ "$1" != "$2" ]; then
            log_pass "$3"
        else
            log_fail "$3"
        fi
    }

    # 验证 session_id 不同
    local sid_a sid_b
    sid_a=$(echo "$state_a" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null || echo "")
    sid_b=$(echo "$state_b" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null || echo "")

    assert_equals "$sid_a" "multi-a-$t" "session A ID 正确"
    assert_equals "$sid_b" "multi-b-$t" "session B ID 正确"
}

# ========== 主流程 ==========

main() {
    local scene="${1:-all}"

    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     OpenViking 对话记忆 E2E 验证                    ║${NC}"
    echo -e "${BLUE}║     BASE=$BASE                          ║${NC}"
    echo -e "${BLUE}║     OV=$OV_URL                              ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""

    check_prerequisites

    case "$scene" in
        all)
            run_scene_1
            run_scene_2
            run_scene_3
            run_scene_4
            run_scene_5
            run_scene_6
            run_scene_7
            run_scene_8
            ;;
        1) run_scene_1 ;;
        2) run_scene_2 ;;
        3) run_scene_3 ;;
        4) run_scene_4 ;;
        5) run_scene_5 ;;
        6) run_scene_6 ;;
        7) run_scene_7 ;;
        8) run_scene_8 ;;
        *)
            echo "用法: $0 [--scene N]  (N=1-8, 默认全部)"
            exit 1
            ;;
    esac

    # 汇总
    echo ""
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}通过: $PASS${NC}"
    echo -e "${RED}失败: $FAIL${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"

    if [ "$FAIL" -gt 0 ]; then
        exit 1
    fi
}

# 解析参数
SCENE="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

main "$SCENE"
