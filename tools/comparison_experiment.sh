#!/usr/bin/env bash
# 基线与HDC-SM方案对比实验（解耦版）
#
# 用法:
#   bash tools/comparison_experiment.sh              # 一键运行全部
#   bash tools/comparison_experiment.sh baseline     # 仅跑基线
#   bash tools/comparison_experiment.sh fullstack    # 仅跑HDC-SM（HDC + SQL 记忆）
#   bash tools/comparison_experiment.sh report       # 从已有 JSON 生成对比报告
#
# 输出: tests/evaluation/output/baseline_vs_fullstack_{timestamp}.md

set -euo pipefail

# ── 配置 ──
# 用例选择：缺省=全量（不传 --ids）；设 IDS 环境变量则按指定用例运行，如:
#   IDS="TC-001 TC-003" bash tools/comparison_experiment.sh baseline
IDS="${IDS:-}"
REPEAT=8
CONCURRENCY=12
TIMEOUT=400
HDC_NAMESPACE="recall_extra"
OUTPUT_DIR="tests/evaluation/output"
STATE_FILE="${OUTPUT_DIR}/.comparison_state"  # 持久化 JSON 路径
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT="${OUTPUT_DIR}/baseline_vs_fullstack_${TIMESTAMP}.md"

mkdir -p "$OUTPUT_DIR"

export STORAGE_BACKEND=sqlite
export LLM_EMBEDDING_PROVIDER=ollama

# ── 工具函数 ──
find_json_report() {
    local log_file="$1"
    grep 'JSON 报告:' "${log_file}" | head -1 | sed 's/.*JSON 报告: //' || echo ""
}

save_state() {
    # 格式: BASELINE_JSON=/path/to/baseline.json
    cat > "$STATE_FILE" <<EOF
BASELINE_JSON="${BASELINE_JSON:-}"
FULLSTACK_JSON="${FULLSTACK_JSON:-}"
BASELINE_LOG="${BASELINE_LOG:-}"
FULLSTACK_LOG="${FULLSTACK_LOG:-}"
IDS="${IDS}"
REPEAT="${REPEAT}"
CONCURRENCY="${CONCURRENCY}"
TIMEOUT="${TIMEOUT}"
HDC_NAMESPACE="${HDC_NAMESPACE}"
EOF
}

load_state() {
    if [ -f "$STATE_FILE" ]; then
        source "$STATE_FILE"
    fi
}

# ── 子命令 ──
CMD="${1:-all}"

# ================================================================
# baseline: 跑基线
# ================================================================
run_baseline() {
    local ts=$(date +%Y%m%d_%H%M%S)
    BASELINE_LOG="${OUTPUT_DIR}/baseline_r${REPEAT}_${ts}.log"

    echo "############################################################"
    echo "# 基线（无 HDC + 无 SQL 记忆）"
    echo "############################################################"
    echo "  用例: ${IDS:-全部}"
    echo "  repeat=${REPEAT}  concurrency=${CONCURRENCY}  timeout=${TIMEOUT}s"
    echo "  日志: ${BASELINE_LOG}"
    echo ""

    export SQL_MEMORY_ENABLED=false

    # 全量（IDS 为空）或指定用例（IDS 非空）
    if [ -n "${IDS}" ]; then
        python -u -m tests.evaluation.cli run \
            --ids ${IDS} \
            --repeat ${REPEAT} \
            --concurrency ${CONCURRENCY} \
            --timeout ${TIMEOUT} \
            -v \
            2>&1 | tee "${BASELINE_LOG}"
    else
        python -u -m tests.evaluation.cli run \
            --repeat ${REPEAT} \
            --concurrency ${CONCURRENCY} \
            --timeout ${TIMEOUT} \
            -v \
            2>&1 | tee "${BASELINE_LOG}"
    fi

    BASELINE_JSON=$(find_json_report "${BASELINE_LOG}")
    echo ""
    echo "基线 JSON: ${BASELINE_JSON}"

    save_state
    echo ""
    echo "✅ 基线完成"
    echo "   下次运行: bash $0 fullstack && bash $0 report"
}

# ================================================================
# fullstack: 跑HDC-SM（HDC + SQL 记忆）
# ================================================================
run_fullstack() {
    local ts=$(date +%Y%m%d_%H%M%S)
    FULLSTACK_LOG="${OUTPUT_DIR}/fullstack_r${REPEAT}_${ts}.log"

    echo "############################################################"
    echo "# HDC-SM（有 HDC + 有 SQL 记忆）"
    echo "############################################################"
    echo "  用例: ${IDS:-全部}"
    echo "  repeat=${REPEAT}  concurrency=${CONCURRENCY}  timeout=${TIMEOUT}s"
    echo "  HDC namespace: ${HDC_NAMESPACE}"
    echo "  日志: ${FULLSTACK_LOG}"
    echo ""

    export SQL_MEMORY_ENABLED=true

    python tools/sql_memory_admin.py status 2>/dev/null || true

    # 全量（IDS 为空）或指定用例（IDS 非空）
    if [ -n "${IDS}" ]; then
        python -u -m tests.evaluation.cli run \
            --ids ${IDS} \
            --repeat ${REPEAT} \
            --concurrency ${CONCURRENCY} \
            --timeout ${TIMEOUT} \
            --with-hdc \
            --hdc-namespace "${HDC_NAMESPACE}" \
            -v --verbose-hdc \
            2>&1 | tee "${FULLSTACK_LOG}"
    else
        python -u -m tests.evaluation.cli run \
            --repeat ${REPEAT} \
            --concurrency ${CONCURRENCY} \
            --timeout ${TIMEOUT} \
            --with-hdc \
            --hdc-namespace "${HDC_NAMESPACE}" \
            -v --verbose-hdc \
            2>&1 | tee "${FULLSTACK_LOG}"
    fi

    FULLSTACK_JSON=$(find_json_report "${FULLSTACK_LOG}")
    echo ""
    echo "HDC-SM JSON: ${FULLSTACK_JSON}"

    save_state
    echo ""
    echo "✅ HDC-SM完成"
    echo "   下次运行: bash $0 report"
}

# ================================================================
# report: 从已有 JSON 生成对比报告
# ================================================================
run_report() {
    load_state

    if [ -z "${BASELINE_JSON:-}" ] || [ -z "${FULLSTACK_JSON:-}" ]; then
        echo "❌ 缺少 JSON 报告文件"
        echo "   基线 JSON: ${BASELINE_JSON:-未设置}"
        echo "   HDC-SM JSON: ${FULLSTACK_JSON:-未设置}"
        echo ""
        echo "   请先运行: bash $0 baseline  或手动设置环境变量:"
        echo "   BASELINE_JSON=/path/to/baseline.json FULLSTACK_JSON=/path/to/fullstack.json bash $0 report"
        exit 1
    fi

    if [ ! -f "${BASELINE_JSON}" ]; then
        echo "❌ 基线 JSON 不存在: ${BASELINE_JSON}"
        exit 1
    fi
    if [ ! -f "${FULLSTACK_JSON}" ]; then
        echo "❌ HDC-SM JSON 不存在: ${FULLSTACK_JSON}"
        exit 1
    fi

    echo "────────────────────────────────────────────────────────────"
    echo "生成对比报告"
    echo "  基线: ${BASELINE_JSON}"
    echo "  HDC-SM: ${FULLSTACK_JSON}"
    echo "  报告: ${REPORT}"
    echo "────────────────────────────────────────────────────────────"

    cat > "$REPORT" <<REPORTEOF
# 基线 vs HDC-SM 对比实验报告

**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**测试用例**: ${IDS:-全部}
**并发度**: ${CONCURRENCY}，repeat: ${REPEAT}（case 内串行），timeout: ${TIMEOUT}s
**HDC**: ${HDC_NAMESPACE}
**SQL 记忆**: 使用已有记录

## 实验设计

| 实验组 | HDC | SQL 记忆 | 说明 |
|--------|-----|---------|------|
| 基线 | 无 | 无 | 纯 Agent NL2SQL 能力 |
| HDC-SM | 有 (${HDC_NAMESPACE}) | 有 | HDC 表结构知识 + SQL 历史记忆 |

## 总览对比

REPORTEOF

    # ── 用 Python 一次性生成全部报告内容 ──
    python -c "
import json, sys

b_json = '${BASELINE_JSON}'
f_json = '${FULLSTACK_JSON}'
report = '${REPORT}'
ids = '${IDS}'
concurrency = ${CONCURRENCY}
repeat = ${REPEAT}
timeout = ${TIMEOUT}
hdc_ns = '${HDC_NAMESPACE}'

with open(b_json) as f:
    b = json.load(f)
with open(f_json) as f:
    f = json.load(f)

# ── 总览 ──
b_pass = f\"{b['passed_cases']}/{b['total_cases']}\"
f_pass = f\"{f['passed_cases']}/{f['total_cases']}\"
b_score = b['average_score']
f_score = f['average_score']
score_delta = f_score - b_score
b_lat = b['average_latency_ms']
f_lat = f['average_latency_ms']
lat_delta = f_lat - b_lat
lat_trend = '📈' if lat_delta < 0 else ('📉' if lat_delta > 0 else '➡️')
score_trend = '📈' if score_delta > 0 else ('📉' if score_delta < 0 else '➡️')
b_ttfb = b.get('average_ttfb_ms') or 0
f_ttfb = f.get('average_ttfb_ms') or 0
b_prep = b.get('average_prep_ms', 0)
f_prep = f.get('average_prep_ms', 0)
b_tools = b['average_tool_calls']
f_tools = f['average_tool_calls']
b_turns = b['average_turns']
f_turns = f['average_turns']
b_tok = b['average_tokens']
f_tok = f['average_tokens']
b_itok = b['average_input_tokens']
f_itok = f['average_input_tokens']
b_otok = b['average_output_tokens']
f_otok = f['average_output_tokens']

overview_rows = []
def row(metric, b_v, f_v, delta='—', trend=''):
    overview_rows.append(f'| {metric} | {b_v} | {f_v} | {delta} | {trend} |')

row('通过率', b_pass, f_pass)
row('平均分', f'{b_score:.2%}', f'{f_score:.2%}', f'{score_delta:+.2%}', score_trend)
row('平均延迟', f'{b_lat:.0f}ms', f'{f_lat:.0f}ms', f'{lat_delta:+.0f}ms', lat_trend)
row('TTFB', f'{b_ttfb:.0f}ms', f'{f_ttfb:.0f}ms')
row('准备耗时', f'{b_prep:.0f}ms', f'{f_prep:.0f}ms')
row('工具调用', f'{b_tools:.1f}', f'{f_tools:.1f}')
row('Turns', f'{b_turns:.1f}', f'{f_turns:.1f}')
row('总 Token', f'{b_tok:.0f}', f'{f_tok:.0f}')
row('输入 Token', f'{b_itok:.0f}', f'{f_itok:.0f}')
row('输出 Token', f'{b_otok:.0f}', f'{f_otok:.0f}')

with open(report, 'a') as out:
    out.write('\n'.join(overview_rows) + '\n\n')

    # ── 维度平均分 ──
    out.write('## 维度平均分对比\n\n')
    out.write('| 维度 | 基线 | HDC-SM | 变化 | 趋势 |\n')
    out.write('|------|------|------|------|------|\n')
    bd = b.get('dimension_averages') or {}
    fd = f.get('dimension_averages') or {}
    labels = {
        'sql_syntax': 'SQL 语法正确',
        'table_column': '表/列引用正确',
        'filter_condition': '过滤条件正确',
        'result_data': '结果数据正确',
        'sql_standard': 'SQL 规范',
    }
    for key in ['sql_syntax', 'table_column', 'filter_condition', 'result_data', 'sql_standard']:
        bv = bd.get(key, 0) or 0
        fv = fd.get(key, 0) or 0
        delta = fv - bv
        trend = '📈' if delta > 0.001 else ('📉' if delta < -0.001 else '➡️')
        label = labels.get(key, key)
        out.write(f'| {label} | {bv:.2%} | {fv:.2%} | {delta:+.2%} | {trend} |\n')
    out.write('\n')

    # ── 逐用例 ──
    out.write('## 逐用例对比\n\n')
    out.write('| 用例 | 难度 | 基线 | HDC-SM | 分数变化 | 延迟变化 | 工具调用 | Token |\n')
    out.write('|------|------|------|------|----------|----------|----------|-------|\n')
    b_cases = {c['test_case']['case_id']: c for c in b.get('case_results', [])}
    f_cases = {c['test_case']['case_id']: c for c in f.get('case_results', [])}

    improved, degraded, unchanged = [], [], []

    for cid in sorted(b_cases.keys(), key=lambda x: int(x.split('-')[1]) if '-' in x else 0):
        bc = b_cases.get(cid)
        fc = f_cases.get(cid)
        if bc is None or fc is None:
            continue
        diff = bc['test_case'].get('difficulty', '')
        b_pass_s = '✅' if bc.get('passed') else '❌'
        f_pass_s = '✅' if fc.get('passed') else '❌'
        bs = bc.get('overall_score', 0)
        fs = fc.get('overall_score', 0)
        sd = fs - bs
        bl = bc.get('duration_ms', 0)
        fl = fc.get('duration_ms', 0)
        be = bc.get('efficiency') or {}
        fe = fc.get('efficiency') or {}
        btools = be.get('tool_call_count', 0)
        ftools = fe.get('tool_call_count', 0)
        btok = be.get('total_tokens', 0)
        ftok = fe.get('total_tokens', 0)

        if sd > 0.005:
            improved.append(cid)
        elif sd < -0.005:
            degraded.append(cid)
        else:
            unchanged.append(cid)

        out.write(f'| {cid} | {diff} | {b_pass_s} {bs:.2%} | {f_pass_s} {fs:.2%} | {sd:+.2%} | {bl}→{fl}ms | {btools}→{ftools} | {btok}→{ftok} |\n')

    out.write('\n')
    if improved:
        out.write(f'**改善的用例 ({len(improved)} 条)**: {\" \".join(improved)}\n')
    if degraded:
        out.write(f'**退化的用例 ({len(degraded)} 条)**: {\" \".join(degraded)}\n')
    if unchanged:
        out.write(f'**无变化的用例 ({len(unchanged)} 条)**: {\" \".join(unchanged)}\n')
    out.write('\n')
" 2>/dev/null

    # ── 报告尾 ──
    cat >> "$REPORT" <<REPORTEOF
## 结论

HDC-SM方案（HDC + SQL 记忆）应比基线方案有以下改善：

1. **准确率提升**: HDC 提供准确的表结构和字段描述，减少表/列幻觉
2. **工具调用减少**: SQL 记忆复用历史成功的 SQL 模式，减少试错查询
3. **延迟变化**: HDC 检索和 SQL 记忆注入会增加少量准备耗时，但可能减少 Agent 盲目探索的轮次

## 原始数据

| 实验组 | JSON 报告 | 日志 |
|--------|----------|------|
| 基线 | \`${BASELINE_JSON}\` | \`${BASELINE_LOG:-N/A}\` |
| HDC-SM | \`${FULLSTACK_JSON}\` | \`${FULLSTACK_LOG:-N/A}\` |
REPORTEOF

    echo ""
    echo "✅ 报告生成完成: ${REPORT}"

    # 如果 matplotlib 可用，自动生成可视化
    if python -c "import matplotlib" 2>/dev/null; then
        echo ""
        local viz_png="${OUTPUT_DIR}/baseline_vs_fullstack_${TIMESTAMP}.png"
        python tools/comparison_viz.py "${BASELINE_JSON}" "${FULLSTACK_JSON}" -o "$viz_png" --dpi 150
        echo "📊 可视化: $viz_png"
    fi
}

# ════════════════════════════════════════════════════════════
# 主逻辑
# ════════════════════════════════════════════════════════════

case "$CMD" in
    baseline)
        BASELINE_LOG="${OUTPUT_DIR}/baseline_r${REPEAT}.log"
        BASELINE_JSON=""
        FULLSTACK_JSON=""
        FULLSTACK_LOG=""
        run_baseline
        ;;

    fullstack)
        load_state
        FULLSTACK_LOG="${OUTPUT_DIR}/fullstack_r${REPEAT}.log"
        run_fullstack
        ;;

    report)
        run_report
        ;;

    all)
        echo "============================================================"
        echo "基线 vs HDC-SM 对比实验"
        echo "============================================================"
        echo "测试用例:    ${IDS:-全部}"
        echo "并发度:      ${CONCURRENCY}"
        echo "repeat:      ${REPEAT}"
        echo "timeout:     ${TIMEOUT}s"
        echo "HDC namespace: ${HDC_NAMESPACE}"
        echo "输出:        ${REPORT}"
        echo ""

        BASELINE_LOG="${OUTPUT_DIR}/baseline_r${REPEAT}.log"
        FULLSTACK_LOG="${OUTPUT_DIR}/fullstack_r${REPEAT}.log"
        BASELINE_JSON=""
        FULLSTACK_JSON=""
        run_baseline
        echo ""
        run_fullstack
        echo ""
        run_report
        ;;

    converge)
        echo "============================================================"
        echo "收敛性分析实验"
        echo "============================================================"
        echo "测试用例:    ${IDS:-全部}"
        echo "并发度:      ${CONCURRENCY}"
        echo "repeat:      10 (一次跑，前缀分析)"
        echo "timeout:     ${TIMEOUT}s"
        echo "HDC namespace: ${HDC_NAMESPACE}"
        echo ""
        local CONVERGE_REPEAT=10
        local ts=$(date +%Y%m%d_%H%M%S)
        BASELINE_LOG="${OUTPUT_DIR}/converge_baseline_r${CONVERGE_REPEAT}_${ts}.log"
        FULLSTACK_LOG="${OUTPUT_DIR}/converge_fullstack_r${CONVERGE_REPEAT}_${ts}.log"

        # 基线
        echo "############################################################"
        echo "# 第 1/2 轮: 基线（无 HDC + 无 SQL 记忆）repeat=${CONVERGE_REPEAT}"
        echo "############################################################"
        export SQL_MEMORY_ENABLED=false
        if [ -n "${IDS}" ]; then
            python -u -m tests.evaluation.cli run \
                --ids ${IDS} \
                --repeat ${CONVERGE_REPEAT} \
                --concurrency ${CONCURRENCY} \
                --timeout ${TIMEOUT} \
                -v \
                2>&1 | tee "${BASELINE_LOG}"
        else
            python -u -m tests.evaluation.cli run \
                --repeat ${CONVERGE_REPEAT} \
                --concurrency ${CONCURRENCY} \
                --timeout ${TIMEOUT} \
                -v \
                2>&1 | tee "${BASELINE_LOG}"
        fi
        BASELINE_JSON=$(find_json_report "${BASELINE_LOG}")
        echo "基线 JSON: ${BASELINE_JSON}"

        # HDC-SM
        echo ""
        echo "############################################################"
        echo "# 第 2/2 轮: HDC-SM（有 HDC + 有 SQL 记忆）repeat=${CONVERGE_REPEAT}"
        echo "############################################################"
        export SQL_MEMORY_ENABLED=true
        python tools/sql_memory_admin.py status 2>/dev/null || true
        if [ -n "${IDS}" ]; then
            python -u -m tests.evaluation.cli run \
                --ids ${IDS} \
                --repeat ${CONVERGE_REPEAT} \
                --concurrency ${CONCURRENCY} \
                --timeout ${TIMEOUT} \
                --with-hdc \
                --hdc-namespace "${HDC_NAMESPACE}" \
                -v --verbose-hdc \
                2>&1 | tee "${FULLSTACK_LOG}"
        else
            python -u -m tests.evaluation.cli run \
                --repeat ${CONVERGE_REPEAT} \
                --concurrency ${CONCURRENCY} \
                --timeout ${TIMEOUT} \
                --with-hdc \
                --hdc-namespace "${HDC_NAMESPACE}" \
                -v --verbose-hdc \
                2>&1 | tee "${FULLSTACK_LOG}"
        fi
        FULLSTACK_JSON=$(find_json_report "${FULLSTACK_LOG}")
        echo "HDC-SM JSON: ${FULLSTACK_JSON}"

        # 收敛性分析
        echo ""
        echo "────────────────────────────────────────────────────────────"
        echo "收敛性分析"
        echo "────────────────────────────────────────────────────────────"
        local converge_md="${OUTPUT_DIR}/convergence_analysis_${ts}.md"
        local converge_png="${OUTPUT_DIR}/convergence_analysis_${ts}.png"
        python tools/convergence_analysis.py \
            "${BASELINE_JSON}" "${FULLSTACK_JSON}" \
            -o "$converge_md" --png "$converge_png"
        echo ""
        echo "✅ 收敛性分析完成"
        echo "   报告: $converge_md"
        echo "   图表: $converge_png"
        ;;

    *)
        echo "用法: bash $0 [baseline | fullstack | report | converge | all]"
        echo ""
        echo "  baseline   仅跑基线测试（无 HDC + 无 SQL 记忆）"
        echo "  fullstack  仅跑HDC-SM测试（有 HDC + 有 SQL 记忆）"
        echo "  report     从已有 JSON 生成对比报告"
        echo "  converge   收敛性分析（run repeat=10，前缀分析）"
        echo "  all        一键运行全部（默认）"
        echo ""
        echo "断点续跑示例:"
        echo "  bash $0 baseline   # 跑完基线后退出"
        echo "  bash $0 fullstack  # 跑HDC-SM"
        echo "  bash $0 report     # 生成报告"
        exit 1
        ;;
esac
