"""
app.datavault — HDC 数据底座模块

提供 HDC 知识库的生成、检索、上传和增量更新能力。
"""

from app.datavault.collector import SchemaCollector
from app.datavault.generator import HDCGenerator
from app.datavault.models import (
    ColumnRaw,
    ColumnSummary,
    DatabaseRaw,
    DatabaseSummary,
    HDCContext,
    TableDescription,
    TableDescriptionWithColumns,
    TableMatch,
    TableRaw,
    TableRelationship,
)
from app.datavault.retriever import HDCRetriever
from app.datavault.uploader import HDCUploader
from app.datavault.updater import HDCUpdater


def get_hdc_retriever(ov_client) -> HDCRetriever:
    """创建 HDC 检索器实例。"""
    return HDCRetriever(ov_client)


def get_hdc_generator(llm_client, collector=None, uploader=None) -> HDCGenerator:
    """创建 HDC 生成器实例。"""
    return HDCGenerator(llm_client=llm_client, collector=collector, uploader=uploader)


__all__ = [
    "SchemaCollector",
    "HDCGenerator",
    "HDCRetriever",
    "HDCUploader",
    "HDCUpdater",
    "ColumnRaw",
    "ColumnSummary",
    "DatabaseRaw",
    "DatabaseSummary",
    "HDCContext",
    "TableDescription",
    "TableDescriptionWithColumns",
    "TableMatch",
    "TableRaw",
    "TableRelationship",
    "get_hdc_retriever",
    "get_hdc_generator",
]