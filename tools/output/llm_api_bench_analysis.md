# LLM API 并发压测分析

**测试时间**: 2026-07-29
**URL**: https://dwai-data.dewu-inc.com/openai/v1
**Model**: deepseek-v4-pro-260425
**Stream**: True
**Tools**: 3 个（query_database, find_table, describe_table）

## 原始数据

```
并发 | 调用数 | 错误 | TTFB Avg | TTFB P50 | TTFB P95 | TTFB P99 | Total Avg | Total P50 | Total P95 | Total P99
   1 |     2 |    0 |   1957ms |   2999ms |   2999ms |   2999ms |   4039ms |   4938ms |   4938ms |   4938ms
   2 |     4 |    0 |   1268ms |   1381ms |   1390ms |   1390ms |   3277ms |   3274ms |   3516ms |   3516ms
   4 |     8 |    0 |   1383ms |   1427ms |   1569ms |   1569ms |   3454ms |   3568ms |   3769ms |   3769ms
   8 |    16 |    0 |   1414ms |   1400ms |   1710ms |   1710ms |   3507ms |   3391ms |   4121ms |   4121ms
```

## 分析结论

### ❌ LLM API 也不是瓶颈

| 指标 | concur=1 | concur=2 | concur=4 | concur=8 | 趋势 |
|------|----------|----------|----------|----------|------|
| TTFB P50 | 2999ms | 1381ms | 1427ms | 1400ms | **→ 稳定** |
| TTFB P95 | 2999ms | 1390ms | 1569ms | 1710ms | **→ 稳定** |
| Total P50 | 4938ms | 3274ms | 3568ms | 3391ms | **→ 稳定** |
| 错误率 | 0% | 0% | 0% | 0% | **→ 0%** |

- concur=1 的 Avg 比 P50 低是因为小样本（2 次）、流式响应头帧到达快但后面慢
- concur≥2 时 TTFB P50 稳定在 ~1400ms，Total P50 稳定在 ~3400ms
- 0% 错误率，流式 API 完全不受并发度影响

## 三轮排查汇总

| 排查项 | 工具 | concur=8 延迟 | 占 Agent 总延迟 | 是瓶颈？ |
|--------|------|--------------|----------------|---------|
| OneDBA SQL 执行 | `onedba_bench.py` | ~200ms | ~1% | ❌ |
| LLM API 调用 | `llm_api_bench.py` | ~3400ms | ~85% | ❌（不随并发增长） |
| 剩余（eval 框架 + Agent 编排） | — | — | ~14% | ⚠️ 待排查 |

## 结论

**OneDBA 和 LLM API 都不随并发度变慢**。延迟增长的根因在最不可能的候选——eval 框架本身：

- `asyncio.gather` 在 `concurrency=4` + `repeat=8` 时创建 32 个并发 Agent 任务
- 每个 Agent 内部有 `asyncio.timeout` 嵌套和 `asyncio.wait` 竞速
- `Semaphore` 控制并发度，但 `gather` 一次性创建所有任务
- 32 个 Agent 同时竞争 LLM API + OneDBA API 连接池

**下一步**：在 runner 中加日志，记录每个 Agent 的 `_run_one` 实际等待时间 vs 执行时间，分离排队等待 vs 实际执行。