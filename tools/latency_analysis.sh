#!/usr/bin/env bash
# 延迟随 repeat 递增分析实验（串行 repeat 方案）
# 用法: bash tools/latency_analysis.sh
#
# 实验目的: 验证串行 repeat 方案下，每次 run 的平均延迟是否随 repeat 增加而保持稳定。
# 旧并行方案中，repeat 之间竞争 semaphore 导致延迟随 repeat 超线性增长。
# 新串行方案中，repeat 逐个执行，每次 run 互不干扰，延迟应保持稳定。
#
# 实验:
#   基线 (无 HDC, 无 SQL memory):  repeat=[1,2,4,8]
#   叠加 (有 HDC, 有 SQL memory):  repeat=[1,2,4,8]
#
# 输出: tools/output/latency_analysis_{timestamp}.md

set -euo pipefail

# ── 配置 ──
IDS="TC-001 TC-003 TC-007 TC-009 TC-013 TC-017 TC-021 TC-024 TC-027 TC-029"
CONCURRENCY=8
TIMEOUT=240
OUTPUT_DIR="tools/output"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT="${OUTPUT_DIR}/latency_analysis_${TIMESTAMP}.md"

mkdir -p "$OUTPUT_DIR"

export STORAGE_BACKEND=sqlite
export LLM_EMBEDDING_PROVIDER=ollama

echo "============================================================"
echo "延迟分析实验 — 串行 repeat 方案验证"
echo "============================================================"
echo "测试用例: ${IDS}"
echo "并发度:   ${CONCURRENCY} (case 间并发)"
echo "repeat:   1, 2, 4, 8 (case 内串行)"
echo "输出:     ${REPORT}"
echo ""

# ── 从日志提取指标 ──
extract() {
    local log_file="$1"
    local key="$2"
    grep "${key}:" "${log_file}" | tail -1 | sed -n "s/.*${key}: \([0-9.]*\).*/\1/p" || echo "N/A"
}

# ── 跑一轮实验 ──
run_exp() {
    local label="$1"
    local flags="$2"
    local repeat="$3"
    local log_file="${OUTPUT_DIR}/${label}_r${repeat}.log"

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "[${label}] repeat=${repeat}"
    echo "────────────────────────────────────────────────────────────"

    python -u -m tests.evaluation.cli run \
        --ids ${IDS} \
        --repeat "${repeat}" \
        --concurrency ${CONCURRENCY} \
        --timeout ${TIMEOUT} \
        ${flags} \
        2>&1 | tee "${log_file}"

    append_row "${label}" "${repeat}" "${log_file}"
}

# ── 追加一行到报告 ──
append_row() {
    local label="$1"
    local repeat="$2"
    local log_file="$3"

    local score=$(extract "${log_file}" "平均分")
    local latency=$(extract "${log_file}" "平均延迟")
    local prep=$(extract "${log_file}" "平均准备耗时")
    local ttfb=$(extract "${log_file}" "平均 TTFB")
    local tools=$(extract "${log_file}" "平均工具调用")
    local turns=$(extract "${log_file}" "平均 Turns")
    local tokens=$(extract "${log_file}" "平均 Token")
    local input=$(extract "${log_file}" "平均输入 Token")
    local output=$(extract "${log_file}" "平均输出 Token")

    # 分数加 %、延迟加 ms
    local score_str="${score}%"
    local latency_str="${latency}ms"
    local prep_str="${prep}ms"
    local ttfb_str="${ttfb}ms"

    cat >> "$REPORT" <<EOF
| ${label} | ${repeat} | ${score_str} | ${latency_str} | ${prep_str} | ${ttfb_str} | ${tools} | ${turns} | ${tokens} | ${input} | ${output} |
EOF

    echo "  ${label} r=${repeat}: 分数=${score_str} 延迟=${latency_str} TTFB=${ttfb_str} Token=${tokens}"
}

# ════════════════════════════════════════════════════════════
# 写报告头
# ════════════════════════════════════════════════════════════
cat > "$REPORT" <<EOF
# 延迟分析实验报告（串行 repeat 方案）

**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**测试用例**: \`${IDS}\`
**并发度**: ${CONCURRENCY} (case 间并发，repeat case 内串行)
**说明**: 每个 case 的 repeat 逐个串行执行，case 之间通过 Semaphore(${CONCURRENCY}) 并发

## 实验目的

验证串行 repeat 方案下，每次 run 的平均延迟是否随 repeat 次数增加而保持稳定。
旧并行方案中，同 case 的 repeat 并发竞争 semaphore(4)，导致延迟随 repeat 超线性增长。
新方案中，repeat 串行执行，每次 run 互不干扰，延迟应保持稳定。

## 实验设计

| 实验组 | HDC | SQL memory | repeat |
|--------|-----|-----------|--------|
| 基线 | 无 | 无 | 1, 2, 4, 8 |
| 叠加 | 有 | 有 | 1, 2, 4, 8 |

## 汇总表

| 实验组 | repeat | 平均分 | 延迟 | 准备耗时 | TTFB | 工具调用 | Turns | 总Token | 输入Token | 输出Token |
|--------|--------|--------|------|----------|------|----------|-------|---------|----------|-----------|
EOF

# ════════════════════════════════════════════════════════════
# 实验 1: 基线 (无 HDC，无 SQL memory)
# ════════════════════════════════════════════════════════════
echo ""
echo "############################################################"
echo "# 基线实验: 无 HDC, 无 SQL memory"
echo "############################################################"

for r in 4; do
    run_exp "基线" "--no-llm-judge --no-quality-judge" "$r"
done


# ════════════════════════════════════════════════════════════
# 实验 2: 叠加 (HDC + SQL memory)
# ════════════════════════════════════════════════════════════
echo ""
echo "############################################################"
echo "# 叠加实验: HDC + SQL memory"
echo "############################################################"

export SQL_MEMORY_ENABLED=true

python tools/sql_memory_admin.py status 2>/dev/null || true

for r in 1 2 4 8; do
    run_exp "叠加" "--with-hdc --no-llm-judge --no-quality-judge --verbose-hdc --hdc-namespace recall_extra" "$r"
done

# ════════════════════════════════════════════════════════════
# 稳定性分析
# ════════════════════════════════════════════════════════════
cat >> "$REPORT" <<EOF

## 稳定性分析

### 关键验证点

1. **延迟稳定性**: 串行 repeat 方案下，每次 run 独立执行无竞争，**平均延迟应不随 repeat 增加而显著变化**。
   - 旧方案预期: r=8 延迟 >> r=1 延迟（semaphore 竞争导致排队）
   - 新方案预期: r=1 ≈ r=2 ≈ r=4 ≈ r=8（允许 ±5% 波动）

2. **TTFB 稳定性**: 首个 LLM 响应时间应稳定在 4-5s，不受 repeat 影响（外部 API 固有延迟）。

3. **Token 稳定性**: 输入/输出 Token 应保持稳定，不随 repeat 膨胀（无会话泄漏）。

4. **工具调用稳定性**: 工具调用次数应保持稳定，Agent 行为不因 repeat 退化。

5. **准备耗时**: prep_ms 保持稳定，串行执行无并发竞争。

### 延迟增幅计算

EOF

# 计算延迟增幅
for label in "基线" "叠加"; do
    echo "### ${label}" >> "$REPORT"
    echo "" >> "$REPORT"
    echo "| repeat | 平均延迟 | 相对 r=1 增幅 |" >> "$REPORT"
    echo "|--------|----------|---------------|" >> "$REPORT"

    base_latency=""
    for r in 1 2 4 8; do
        log="${OUTPUT_DIR}/${label}_r${r}.log"
        latency=$(extract "${log}" "平均延迟")
        if [ "$r" = "1" ]; then
            base_latency="$latency"
            echo "| ${r} | ${latency}ms | — (基准) |" >> "$REPORT"
        elif [ "$base_latency" != "N/A" ] && [ "$latency" != "N/A" ]; then
            # 用 awk 计算增幅百分比
            increase=$(awk "BEGIN {printf \"%.1f\", ($latency - $base_latency) / $base_latency * 100}")
            echo "| ${r} | ${latency}ms | ${increase}% |" >> "$REPORT"
        else
            echo "| ${r} | ${latency}ms | N/A |" >> "$REPORT"
        fi
    done
    echo "" >> "$REPORT"
done

# ── 结论 ──
cat >> "$REPORT" <<EOF
## 结论

### 期望结果

串行 repeat 方案消除了同 case 内 repeat 之间的 semaphore 竞争，每次 run 的执行环境完全独立。
因此，**平均延迟应在所有 repeat 级别上保持稳定**（允许 ±5% 的正常波动）。

### 对比旧方案

| 维度 | 旧并行方案 | 新串行方案 |
|------|-----------|-----------|
| repeat 执行方式 | case 内并发 (asyncio.gather) | case 内串行 (for loop) |
| 内层并发限制 | Semaphore(4) 硬编码 | 无（自然串行） |
| 最大并发 Agent 数 | ~16 (concurrency × 4) | = concurrency |
| 延迟 vs repeat | 随 repeat 超线性增长 | 稳定（不随 repeat 变化） |
| 总 wall time | 较短（repeat 并发） | 较长（repeat 串行） |
| 延迟测量可靠性 | 低（受竞争干扰） | 高（环境一致） |

### 验证标准

- ✅ 通过: 基线/叠加两组 r=1→r=8 的延迟增幅均 < 10%
- ⚠️ 待观察: 某组增幅在 10-20% 之间
- ❌ 失败: 某组增幅 > 20%，需要排查原因

## 原始日志

| 实验组 | repeat | 日志文件 |
|--------|--------|---------|
EOF

for label in "基线" "叠加"; do
    for r in 1 2 4 8; do
        echo "| ${label} | ${r} | ${OUTPUT_DIR}/${label}_r${r}.log |" >> "$REPORT"
    done
done

echo ""
echo "============================================================"
echo "实验完成"
echo "报告: ${REPORT}"
echo "============================================================"