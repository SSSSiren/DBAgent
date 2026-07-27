# Brief: hdc-retrieval-optimization

## Problem

HDC 知识库膨胀后检索准确率下降。评测数据显示：当知识库从 6 表（complete）膨胀到 11 表（overcomplete），通过率从 96.4% 降至 89.3%，平均延迟从 95s 回升至 114s。根因分析揭示五层影响因素：

1. **Top-60 占比稀释**：L2 文件数从 130 增至 270，`limit=60` 的固定检索窗口占比从 46% 降至 22%，正确表的列被噪音表列挤出候选集
2. **score_threshold 缺失**：默认 threshold=0，低分噪音（0.1~0.3）不过滤，占据检索名额
3. **表评分无累积证据**：表最终分 = max(单列分)，多列匹配的正确表可能被单列高分的噪音表"偷排名"
4. **无 L0/L1 层级**：memory 路径下 `semantic_status="skipped"`，QUICK 模式无 Rerank 可用，无法进行语义重排序
5. **相似表混淆**：overcomplete 中 3 张告警表同时注入 LLM 上下文，导致表选择混淆和选择瘫痪

## Current State

- **HDC 存储路径**：`viking://user/hdc-system/memories/hdc`（memory 路径），硬编码 `semantic_status="skipped"`，不生成 L0/L1
- **目录结构**：每张表目录下包含 `_INDEX.md`（表描述）和 30 个列 `.md` 文件，全部为 L2
- **检索参数**：`find(level=[2], limit=60)`，无 `score_threshold`
- **表评分**：`max(单列向量分)`，无累积证据
- **表去重**：无，相似表可能同时进入 Top 5

## Desired Outcome

1. HDC 知识库的**表目录**拥有 L0/L1，使 THINKING 模式的 Rerank 可用
2. 大知识库（400 表+）的检索准确率不随规模显著退化
3. 向量检索的噪音比例可控，低分噪音被过滤
4. 多列匹配的表在排名上优于单列匹配的噪音表
5. 同一业务实体下的相似表不会同时占据 Top 5 多个位置

## Approach

**切换存储路径 + 列下沉 + 检索参数优化 + 实体去重**

将 HDC 根路径从 memory 路径切回 resources 路径（`viking://resources/hdc`），利用 OpenViking 的 `_write_direct_with_refresh` 自动触发 SemanticProcessor 生成 L0/L1。同时将列文件下沉到 `_columns/` 子目录，使每表目录仅含 1 个 `_INDEX.md` 文件，控制 SemanticProcessor 的 LLM 调用量从 32 次/表降至 2 次/表（降低 16 倍）。

检索侧三项优化：`limit` 从 60 提高到 200、新增 `score_threshold=0.25` 过滤低分噪音、Stage 1 从 `level=[2]` 改为 `level=[0,1]` 利用 L0/L1 快速定位。表评分改为 `sum(top-3 列分)` 累积多列证据。Top 5 截断前加入 `main_entity` 爆炸半径控制（同实体最多 2 张表）。

**为什么选这个方案**：所有改动在 DBAgent 侧完成，不改 OpenViking。成本最低（800 次额外 LLM 调用）且收益最大（L0/L1 + Rerank + 噪音过滤 + 去重 四重改善）。

## Scope

- **In**:
  - `uploader.py`：`_HDC_ROOT` 路径迁移、`_columns/` 子目录创建、列文件写入路径变更
  - `retriever.py`：`limit` 调整、`score_threshold` 新增、`level` 调整、表评分逻辑改进、`main_entity` 爆炸半径控制、列检索 `target_uri` 适配
  - `generator.py`：无需改动（LLM 产出内容不变）
  - `collector.py`：无需改动
  - 测试：新增检索准确率回归测试、`_columns/` 路径兼容性测试

- **Out**:
  - OpenViking 源码改动
  - Rerank 服务部署（后续独立 spec）
  - 评测框架改动
  - HDC 生成 LLM prompt 改动

## Boundary Candidates

- **uploader 路径与目录重构**：独立于 retriever 优化，可先完成路径迁移验证 L0/L1 生成，再做检索优化
- **retriever 参数优化**：`limit`/`score_threshold`/`level` 调整是纯参数变更，可独立于评分逻辑改动
- **retriever 评分与去重**：表评分 `sum(top-3)` 和 `main_entity` 爆炸半径控制是算法改进，可独立于参数调优

## Out of Boundary

- 不涉及 OpenViking 的 Rerank 服务部署或配置
- 不涉及 THINKING 模式的启用（L0/L1 生成后 THINKING 模式立即可用，但需 OpenViking 侧配置 RerankConfig）
- 不涉及 `collector.py` 或 `generator.py` 的 LLM prompt 修改
- 不涉及评测框架的 CLI 或报告格式变更

## Upstream / Downstream

- **Upstream**:
  - `hdc-datavault-knowledge-base`（已完成）：现有 HDC 生成/检索/上传管线是本次优化的基础
  - OpenViking：resources 路径的 SemanticProcessor 自动生成 L0/L1
  - OneDBA：schema 采集能力不变

- **Downstream**:
  - Rerank 接入 spec（后续）：THINKING 模式需要 OpenViking 配置 RerankConfig
  - 评测对比 spec（后续）：基于优化后的检索效果做新一轮 complete/overcomplete 对比评测

## Existing Spec Touchpoints

- **Extends**: `hdc-datavault-knowledge-base` — 在已完成的上传/检索管线上做增强
- **Adjacent**: `hdc-eval-enhance` — 评测框架在本 spec 范围外，但可用于验证优化效果

## Constraints

- 不改动 OpenViking 源码
- 资源路径下 `write(wait=True)` 需等待 SemanticProcessor 完成，单表 2 次 LLM 调用（1 摘要 + 1 概览），估算 400 表总计 800 次调用
- 列文件在 `_columns/` 子目录下，`find()` 检索时需调整 `target_uri` 指向子目录
- 向后兼容：已有的 memory 路径知识库不自动迁移，需重建