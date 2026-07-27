# 需求文档

## Introduction

DBAgent 的 HDC（层次化数据上下文）知识库在规模膨胀后出现检索准确率下降。评测数据显示：当知识库从 6 表（complete 场景）膨胀到 11 表（overcomplete 场景），通过率从 96.4% 降至 89.3%，平均延迟从 95s 回升至 114s，平均工具调用从 1.0 回升至 1.2。

根因分析揭示五层影响因素：固定大小的检索窗口（top-60）在知识库文件数增长后占比稀释，正确表的列被噪音表列挤出候选集；score_threshold 缺失导致低分噪音不过滤；表评分仅取单列最高分，无法累积多列匹配的证据；缺乏 L0/L1 层级摘要使语义重排序不可用；同一业务实体下的相似表同时注入 LLM 上下文导致表选择混淆。

本项目通过四项改进提升 HDC 检索准确率的大规模鲁棒性：生成表级 L0/L1 层级摘要、优化检索参数（窗口大小、分数阈值、检索层级）、改进表评分算法（多列证据累积）和业务实体去重。所有改动在 DBAgent 侧完成，不修改 OpenViking 源码。

## Boundary Context

- **In scope**: HDC 知识库的存储路径迁移（从 memory 路径到 resources 路径）、目录结构重构（列文件下沉至独立子目录）、在线检索参数优化（limit、score_threshold、level）、表评分算法改进（多列证据累积）、业务实体去重（同实体表数量限制）、向后兼容旧格式知识库
- **Out of scope**: OpenViking 源码改动、Rerank 服务部署或配置、THINKING 模式的启用（需 OpenViking 侧配置 RerankConfig）、collector 或 generator 的 LLM prompt 修改、评测框架改动
- **Adjacent expectations**: OpenViking 的 SemanticProcessor 在 resources 路径下自动生成 L0/L1；已有 memory 路径的 HDC 知识库不自动迁移，需通过重新生成完成升级

## Requirements

### Requirement 1: L0/L1 层级摘要生成

**Objective:** 作为 HDC 知识库管理员，我希望生成的知识库包含表级 L0/L1 语义摘要，使在线检索能利用层级摘要快速定位相关表，替代逐列全文检索。

#### Acceptance Criteria

1. When HDC 知识库生成触发，the DBAgent HDC 子系统 shall 将表描述与列描述分别存储——表描述写入表目录、列描述写入表目录的独立子目录，使 OpenViking SemanticProcessor 仅基于表描述文件生成该目录的 L0（.abstract.md）和 L1（.overview.md）层级摘要。
2. When L0/L1 生成完成后，the DBAgent HDC 子系统 shall 在在线检索阶段使用 level=[0,1] 进行表级语义搜索，以 L0/L1 的语义摘要而非列级原文全文作为检索匹配目标。
3. If SemanticProcessor 在生成某张表的 L0/L1 时失败或超时，the DBAgent HDC 子系统 shall 记录警告日志并继续处理其余表，不中断整体知识库生成流程。
4. Where 列描述内容写入子目录，the DBAgent HDC 子系统 shall 在检索列信息时自动指向该子目录，行为与迁移前一致。

### Requirement 2: 检索参数优化

**Objective:** 作为 Agent，我希望 HDC 检索能在知识库规模扩大后保持稳定的准确率，低分噪音不被纳入候选集，正确表的列不被挤出检索窗口。

#### Acceptance Criteria

1. When 用户发起对话并触发 HDC 检索，the DBAgent HDC 子系统 shall 使用不小于 200 的检索窗口（limit），确保在 400 表以上规模的知识库中正确表的相关描述仍能进入候选集。
2. When 向量检索返回匹配结果，the DBAgent HDC 子系统 shall 过滤掉相似度分数低于 0.25 的结果，减少低分噪音对候选集排序的干扰。
3. If 过滤后无候选结果，the DBAgent HDC 子系统 shall 静默降级并返回空结果，不阻塞正常对话流程。

### Requirement 3: 表评分多列证据累积

**Objective:** 作为 Agent，我希望表的检索排名能反映多列匹配的累积证据，而非仅取决于单列的最高分，避免单列偶然高分的噪音表在排名上超越多列匹配的正确表。

#### Acceptance Criteria

1. When 同一张表有多个列匹配用户查询，the DBAgent HDC 子系统 shall 累积得分最高的前 3 列的分数作为该表的综合评分，而非仅取单列最高分。
2. When 表评分完成后，the DBAgent HDC 子系统 shall 按综合评分降序排列候选表，使多列匹配的正确表在排名上优于单列偶然匹配的噪音表。

### Requirement 4: 业务实体去重

**Objective:** 作为 Agent，我希望注入上下文的候选表在业务域层面具有多样性，避免同一业务实体下的多张相似表同时占满 Top 5 位置，导致 LLM 表选择混淆。

#### Acceptance Criteria

1. When 候选表按评分排序后，the DBAgent HDC 子系统 shall 在截断 Top 5 前，限制同一业务实体（main_entity）下最多 2 张表进入最终结果，将超出限制的表跳过并由后续排名的表递补。
2. Where 某张表的 main_entity 无法解析（如为空），the DBAgent HDC 子系统 shall 以该表的表名作为实体标识，回退到不出错的默认行为，不中断检索流程。

### Requirement 5: 向后兼容与降级

**Objective:** 作为 DBA 管理员，我希望已有的旧格式 HDC 知识库在路径和结构变更后仍能正常使用，不因格式变更而中断线上服务。

#### Acceptance Criteria

1. If HDC 检索时访问的是旧格式知识库（无 L0/L1 层级摘要），the DBAgent HDC 子系统 shall 自动回退到 level=[2] 的 L2 全文检索模式，不因路径迁移而中断已有知识库的正常使用。
2. Where 管理员需要将旧格式知识库升级为新格式，the DBAgent HDC 子系统 shall 通过重新生成操作完成迁移，不提供自动就地迁移机制。