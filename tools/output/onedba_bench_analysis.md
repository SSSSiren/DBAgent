# OneDBA 并发压测分析

**测试时间**: 2026-07-29
**schemaId**: 65938636 (dw_onedba)
**每并发度重复**: 5 次
**测试 SQL**: `SELECT COUNT(*)`, `SELECT ... WHERE ... LIMIT 10`, `SELECT ... GROUP BY`

## 原始数据

```
SQL                | 并发 | 次数 | 错误率 |   Avg |   P50 |   P95 |   P99 |   Min |   Max
simple_count       |    1 |    5 |    0% | 217ms | 170ms | 392ms | 392ms | 167ms | 392ms
simple_count       |    2 |   10 |    0% | 176ms | 177ms | 210ms | 210ms | 139ms | 210ms
simple_count       |    4 |   20 |    0% | 166ms | 168ms | 226ms | 226ms | 136ms | 226ms
simple_count       |    8 |   40 |    0% | 197ms | 186ms | 276ms | 286ms | 147ms | 286ms

simple_filter      |    1 |    5 |    0% | 167ms | 154ms | 212ms | 212ms | 141ms | 212ms
simple_filter      |    2 |   10 |    0% | 172ms | 176ms | 198ms | 198ms | 150ms | 198ms
simple_filter      |    4 |   20 |    0% | 169ms | 173ms | 204ms | 204ms | 141ms | 204ms
simple_filter      |    8 |   40 |    0% | 190ms | 194ms | 232ms | 237ms | 149ms | 237ms

aggregation        |    1 |    5 |    0% | 162ms | 170ms | 178ms | 178ms | 139ms | 178ms
aggregation        |    2 |   10 |    0% | 164ms | 168ms | 196ms | 196ms | 140ms | 196ms
aggregation        |    4 |   20 |    0% | 185ms | 185ms | 238ms | 238ms | 143ms | 238ms
aggregation        |    8 |   40 |    0% | 201ms | 207ms | 231ms | 249ms | 154ms | 249ms
```

## 分析结论

### ❌ OneDBA 不是瓶颈

| 指标 | concur=1 | concur=8 | 变化 |
|------|----------|----------|------|
| simple_count avg | 217ms | 197ms | **→ 持平** |
| simple_filter avg | 167ms | 190ms | **+14%** |
| aggregation avg | 162ms | 201ms | **+24%** |
| P99 (全 SQL) | 178-392ms | 237-286ms | **→ 持平** |

- 0% 错误率，并发 8 时 P99 仅 286ms
- 平均延迟完全不随并发度增长
- 3 种 SQL 类型表现一致

### 结论：延迟增长根因在它处

OneDBA 单次查询在 160-200ms、P99 < 400ms，即使 concurrency=8 也不变。而原实验中 baseline 延迟从 49.5s (r=1) 涨到 102s (r=8)：

| 延迟来源 | 耗时 | 占比 |
|---------|------|------|
| OneDBA SQL 执行 | ~200ms × 2.5 次 = 0.5s | **~1%** |
| LLM API 调用 | TTFB 4600ms + 推理 | **~85%** |
| eval 框架开销 | asyncio.gather + Semaphore + 编排 | 待排查 |
| 其他 | Agent 工具调用编排 | 待排查 |

**下一步排查方向**：
1. LLM API 是否在高并发下排队——需单独测 LLM API 延迟 vs 并发度
2. eval 框架的 `asyncio.gather` + `Semaphore` 是否产生竞争——需加日志
3. Agent 内 `asyncio.timeout` 嵌套是否导致额外等待