"""
HDC 数据模型 — 定义采集层、生成层、检索层的所有数据结构。

采集层（原始 schema）: ColumnRaw, TableRaw, DatabaseRaw
生成层（LLM 输出）: ColumnSummary, TableDescription, TableRelationship, DatabaseSummary
聚合层:            TableDescriptionWithColumns
检索层:            HDCContext, TableMatch
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ═══════════════════════════════════════════════════════════════
# 采集层 — 从 OneDBA 采集的原始 schema 数据
# ═══════════════════════════════════════════════════════════════


@dataclass
class ColumnRaw:
    """原始列信息（来自 DESCRIBE）"""
    name: str
    data_type: str           # e.g. "varchar(32)", "bigint", "decimal(12,2)"
    nullable: bool
    key: str = ""            # "PRI" / "UNI" / "MUL" / ""
    default: str = ""
    extra: str = ""          # "auto_increment", "on update CURRENT_TIMESTAMP", etc.


@dataclass
class TableRaw:
    """原始表信息（来自 SHOW TABLE STATUS）"""
    name: str
    comment: str = ""
    engine: str = ""
    row_count_estimate: int = 0
    columns: list[ColumnRaw] = field(default_factory=list)
    sample_rows: list[dict[str, object]] = field(default_factory=list)


@dataclass
class DatabaseRaw:
    """原始数据库信息"""
    schema_id: int
    tables: list[TableRaw] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 生成层 — LLM 生成的 HDC 结构化输出
# ═══════════════════════════════════════════════════════════════


@dataclass
class ColumnSummary:
    """列摘要（LLM 生成）"""
    column_name: str
    description: str          # 自然语言业务描述
    sample_values: list[str] = field(default_factory=list)
    data_type: str = ""
    nullable: bool = False
    is_primary_key: bool = False
    column_comment: str = ""


@dataclass
class TableDescription:
    """表描述（LLM 生成）"""
    table_name: str = ""
    main_entity: str = ""     # 核心实体 + 同义词，用 / 分隔，e.g. "售后/退货/退款/换货"
    table_type: Literal["fact", "dimension", "bridge"] = "fact"
    primary_key: str = ""
    key_attributes: list[str] = field(default_factory=list)  # top 5 关键业务属性
    description: str = ""     # 自然语言业务描述
    usage_scenario: str = ""  # 使用场景：何时使用此表而非其他相似表
    row_count_estimate: int = 0


@dataclass
class TableRelationship:
    """表关系（LLM 生成）"""
    source_table: str = ""
    target_table: str = ""
    relationship_type: str = ""        # "one_to_one" | "one_to_many" | "many_to_many"
    join_columns: list[tuple[str, str]] = field(default_factory=list)  # [(source_col, target_col)]
    confidence: float = 0.0
    description: str = ""


@dataclass
class DatabaseSummary:
    """数据库摘要（LLM 生成）"""
    database_name: str = ""
    representative_entities: list[str] = field(default_factory=list)  # e.g. ["订单", "用户", "商品"]
    domain_hint: str = ""               # e.g. "电商交易域"
    description: str = ""
    table_count: int = 0


# ═══════════════════════════════════════════════════════════════
# 聚合层 — 表描述 + 关联的列摘要列表
# ═══════════════════════════════════════════════════════════════


@dataclass
class TableDescriptionWithColumns:
    """表描述与其关联的全部列摘要（用于生成和上传）"""
    table_name: str = ""
    main_entity: str = ""
    table_type: Literal["fact", "dimension", "bridge"] = "fact"
    primary_key: str = ""
    key_attributes: list[str] = field(default_factory=list)
    description: str = ""
    usage_scenario: str = ""  # 使用场景：何时使用此表而非其他相似表
    row_count_estimate: int = 0
    columns: list[ColumnSummary] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 检索层 — HDC 检索输出，注入 Agent 上下文
# ═══════════════════════════════════════════════════════════════


@dataclass
class TableMatch:
    """单张匹配表的检索结果"""
    table_name: str
    main_entity: str
    table_type: str
    description: str
    usage_scenario: str = ""  # 使用场景：何时使用此表而非其他相似表
    row_count_estimate: int = 0
    relevant_columns: list[str] = field(default_factory=list)  # 列描述列表，最多 6 列


@dataclass
class HDCContext:
    """HDC 检索的完整上下文"""
    database_summary: str = ""
    matched_tables: list[TableMatch] = field(default_factory=list)
