# 需求文档

## 介绍

增强 HDC 数据底座评测框架，使其能够准确衡量 HDC 对 Agent NL2SQL 表现的真实影响。

**谁有这个问题**：DBAgent 开发者需要评估 HDC 数据底座是否真正提升了 Agent 的 SQL 生成质量，但目前评测框架只测量最终 SQL 正确性，无法回答"HDC 减少了多少次 find_table 调用"、"Agent 是否采纳了 HDC 提供的正确表名"等关键问题。

**当前状况**：现有评测框架的 `--compare-hdc` 模式已能执行两轮评测（基线 vs HDC），`tool_call_details` 字典已收集每次工具调用次数，HDC debug 脚本已验证 HDC 上下文内容正确。但对比报告仅展现全局指标差异（总分、通过率、总工具调用次数），缺少：
1. 逐工具类别的调用次数对比
2. HDC 内容正确性审计
3. 首轮准确性追踪

**应该变成什么**：评测框架在 `--compare-hdc` 模式下，除了现有全局对比外，还应输出逐工具调用效率对比、HDC 正确性审计、首轮表名准确性，并通过 `--verbose-hdc` 参数支持实时注入状态输出。

## 边界上下文（可选）

- **范围内**：评测对比报告的增强渲染（新增逐工具效率对比表、HDC 正确性审计表、首轮准确性指标）；评测运行时的 HDC 注入验证逻辑；CLI 的 `--verbose-hdc` 参数及实时输出
- **范围外**：HDC 知识库的生成、检索或存储逻辑；Agent 系统提示词或行为策略；评分公式或通过标准的修改；通用 A/B 对比模式（非 HDC 场景）
- **相邻期望**：评测框架继续通过现有的 `_inject_hdc_context()` 注入 HDC 上下文；`tool_call_details` 字典由 `_execute_agent_once()` 正常收集；参考表名从 `TestCase.reference_sql` 中可提取

## 需求

### 需求 1：逐工具调用效率对比

**目标**：作为评测人员，我希望在 HDC 对比报告中看到每种工具调用次数的基线 vs HDC 差异，以便判断 HDC 具体节省了哪类工具的调用。

#### 验收标准

1. When `--compare-hdc` 模式生成对比报告时，the 评测系统 shall 在报告中包含"工具调用效率对比"章节，列出 find_table、describe_table、query_database 三种关键工具在基线和 HDC 下的平均调用次数及变化量。
2. The 评测系统 shall 对每种工具分别标注效率趋势（调用减少为改善、增加为退化）。
3. Where 某条用例的某工具调用次数在基线和 HDC 下均为零，the 评测系统 shall 在该行显示"0"而非留空。
4. The 逐工具对比数据 shall 与现有的全局工具调用总次数（`average_tool_calls`）保持一致（即各工具次数之和等于总次数）。

---

### 需求 2：HDC 注入正确性审计

**目标**：作为评测人员，我希望知道每条用例的 HDC 上下文是否包含了参考 SQL 中的正确表名，以及 Agent 实际使用了什么表名，以便区分"HDC 生成错误"和"Agent 忽略 HDC"两类问题。

#### 验收标准

1. When `--compare-hdc` 模式的有 HDC 轮次执行时，the 评测系统 shall 从注入的 HDC 上下文中提取出现的所有表名，并检查参考 SQL 中的表名是否在 HDC 上下文文本中出现。
2. When `--compare-hdc` 模式的有 HDC 轮次执行时，the 评测系统 shall 从 Agent 生成的 SQL 或工具调用参数中提取 Agent 实际使用的表名。
3. When 对比报告生成时，the 评测系统 shall 包含"HDC 正确性审计"章节，逐条展示：用例 ID、HDC 是否包含正确表名、Agent 实际使用的表名、Agent 是否使用了正确表名、是否存在幻觉表名（表名既不在 HDC 上下文中也不在参考 SQL 中）。
4. If Agent 实际使用的表名在数据库 schema 中不存在（如表名拼写截断），the 评测系统 shall 标注为"幻觉"。
5. The 评测系统 shall 在审计章节末尾输出聚合统计：HDC 正确包含表名的用例数、Agent 采纳正确表名的用例数、Agent 产生幻觉表名的用例数。

---

### 需求 3：首轮表名准确性追踪

**目标**：作为评测人员，我希望知道 Agent 是否在首次查询时就使用了正确的表名，以及是否在查询前调用了 find_table 进行探索，以便衡量 HDC 对减少探索性工具调用的效果。

#### 验收标准

1. When Agent 执行完毕后，the 评测系统 shall 记录 Agent 第一个调用的工具名称和第一个查询类工具（query_database 或 execute_sql）使用的表名。
2. When Agent 执行完毕后，the 评测系统 shall 记录 Agent 在首次查询之前是否调用了 find_table。
3. When `--compare-hdc` 报告渲染时，the 评测系统 shall 在逐用例对比表中增加"首轮正确"列，展示 Agent 首次查询是否使用了参考 SQL 中的正确表名。
4. When 对比报告渲染时，the 评测系统 shall 在工具调用效率对比章节汇总首轮 find_table 调用率（调用了 find_table 的用例数 / 总用例数），对比基线 vs HDC 的差异。

---

### 需求 4：HDC 注入状态实时输出

**目标**：作为评测人员，我希望在执行 `--compare-hdc` 评测时能实时看到每条用例的 HDC 注入状态，以便快速判断 HDC 服务是否正常工作。

#### 验收标准

1. Where 用户使用了 `--verbose-hdc` 参数，the 评测系统 shall 在每条用例开始执行后，立即打印一行 HDC 注入状态：包含用例 ID、注入字符数、是否包含正确表名。
2. When `--compare-hdc` 评测全部完成后，the 评测系统 shall 在终端打印 HDC 注入摘要：成功注入用例数/总用例数、正确表名在上下文中的用例数、Agent 采纳正确表名的用例数、Agent 产生幻觉表名的用例数。
3. If HDC 注入失败（OpenViking 不可达或检索异常），the 评测系统 shall 在实时输出中标注警告，但不中断评测流程。
4. Where 用户未使用 `--verbose-hdc` 参数，the 评测系统 shall 不在终端输出每条用例的 HDC 注入状态（保持现有输出格式不变）。

---

### 需求 5：向后兼容

**目标**：作为现有评测流程的使用者，我希望新增的评测能力不影响现有评测模式的运行，已有的 `--with-hdc` 单轮模式和 `--compare-hdc` 对比模式的输出格式保持不变。

#### 验收标准

1. When 使用 `--with-hdc` 单轮模式（非 `--compare-hdc`）运行评测时，the 评测系统 shall 不修改现有的报告结构和终端输出格式。
2. When 使用 `--compare-hdc` 对比模式但未使用 `--verbose-hdc` 时，the 评测系统 shall 在现有报告章节之后追加新章节，不删除或重排现有章节。
3. The 现有 JSON 报告的数据结构 shall 保持向后兼容——新增字段通过可选字段追加，不修改现有字段的类型或语义。
4. The 现有 Markdown 报告的章节顺序 shall 保持不变（总览 → 维度平均分 → 按难度分布 → 用例详情 → 失败详情 → 稳定性分析），新增章节追加在此之后。
