# 技术调研日志

## 调研范围

本次调研聚焦于 HDC 检索优化方案的技术可行性，重点验证：

1. OpenViking resources 路径的 SemanticProcessor 对 `.md` 文件的处理方式
2. 目录结构变更对现有 updater/retriever 的兼容性影响
3. 检索参数优化和评分算法的改进空间

## 关键发现

### 1. SemanticProcessor 对纯文本文件使用普通 LLM

**来源**：`openviking/storage/queuefs/semantic_processor.py` 第 1156-1162 行

`_generate_single_file_summary` 按文件类型分发：
- 图片/音频/视频 → VLM（视觉模型）
- 其他（包括 `.md`）→ `_generate_text_summary` → `vlm.get_completion_async(prompt)`（普通 LLM）

**结论**：HDC 的 `.md` 文件不会触发 VLM，走普通 LLM。之前 memory 路径的 VLM 超时问题是并发量过大（31 文件/表 × 400 表 = 12,400 次调用）而非模型类型问题。

**影响**：切换到 resources 路径 + 列下沉后，每表仅 1 个 `_INDEX.md` 触发 SemanticProcessor，LLM 调用量降至 2 次/表（1 摘要 + 1 概览），总计 800 次。在 `max_concurrent=64` 的限流下不会超时。

### 2. resources 路径自动触发 SemanticProcessor

**来源**：`openviking/storage/content_write.py` 第 85-101 行

```python
context_type = context_type_for_uri(normalized_uri)
if context_type == "memory":
    return await self._write_memory_with_refresh(...)  # semantic_status="skipped"
return await self._write_direct_with_refresh(...)       # _enqueue_semantic_refresh()
```

**结论**：只需将 `_HDC_ROOT` 从 `viking://user/.../memories/hdc` 改为 `viking://resources/hdc`，OpenViking 的 write 管线自动分发到 `_write_direct_with_refresh`，触发 SemanticProcessor 生成 L0/L1。

### 3. 增量更新完全兼容新目录结构

**来源**：`app/datavault/updater.py` 第 79-188 行

`_get_stored_state` 通过 `fs/ls _tables/` 列出表目录，`_tables/` 的直接子目录只有表目录。`_columns/` 在 `_tables/{table}/_columns/` 下，不在 `_tables/` 的直接列表中，对增量更新完全透明。

`_store_hash` 和 `check_and_update` 中的 `_INDEX.md` 路径不变，tags 读写不变。

**结论**：updater.py 零改动，所有现有功能（全量/限量增量更新、hash 对比、表删除）自动兼容。

## 设计决策

### 决策 1：列下沉到 `_columns/` 子目录而非 flatten 到 `_tables/` 下

**选项 A**：列文件保持与 `_INDEX.md` 同级 → SemanticProcessor 处理 31 文件/表，LLM 调用 12,400 次
**选项 B**：列文件下沉到 `_columns/` 子目录 → SemanticProcessor 处理 1 文件/表，LLM 调用 800 次

**选择**：B。成本降低 16 倍，且不影响检索——列检索原本就指向 `_table_dir_uri`，改为 `_columns_dir_uri` 即可。

### 决策 2：表评分算法从 max 改为 sum(top-3)

**选项 A**：max(单列分) → 单列噪音表可能超越多列正确表
**选项 B**：mean(所有列分) → 大量低分列稀释高分列
**选项 C**：sum(top-3) → 累积多列证据，抑制稀释

**选择**：C。top-3 在累积证据和抑制稀释之间取得平衡。3 列是一个表中与查询相关的典型列数量。

### 决策 3：不使用独立的评分/去重类

**选项 A**：新建 `ScoreAggregator` 和 `EntityDeduplicator` 类
**选项 B**：内嵌在 `retrieve()` 方法中

**选择**：B。评分是 5 行代码（defaultdict + sorted + sum），去重是 10 行代码（dict + filter）。两个"算法"都只有一个调用点，提取为独立类是不必要的抽象。

### 决策 4：旧格式兼容采用自动回退而非自动迁移

**选项 A**：检测到旧格式时自动重建
**选项 B**：检测到旧格式时回退到 L2 检索，管理员手动触发重建

**选择**：B。自动重建可能意外触发大量 LLM 调用（100+ 表），且管理员可能不希望自动变更知识库格式。

## 风险

1. **SemanticProcessor 队列延迟**：800 次 LLM 调用在 `max_concurrent=64` 下可能排队，但 `wait=True` 的单表等待时间（2 次调用）在秒级。风险：低。
2. **`_extract_table_name` 对 `_columns/` 路径的适配**：当前逻辑对 column `.md` 文件取 `parts[-2]` 作为表名。`_columns/col.md` 的 `parts[-2]` 是 `_columns` 而非表名。需要新增 `_columns/` 路径识别。风险：中，需在实现时仔细处理。
3. **旧格式与列下沉目录共存**：如果用户对新格式知识库执行增量更新，updater 会为新表创建 `_columns/` 子目录，旧表仍保持扁平结构。retriever 的 `_retrieve_columns` 需要同时兼容两种路径。风险：中，已在设计中通过回退逻辑覆盖。