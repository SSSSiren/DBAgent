#!/usr/bin/env python3
"""
RAG 数据初始化脚本

使用方式：
    python scripts/init_rag.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.initialize import initialize_from_files
from app.config import settings


def main():
    print("开始初始化 RAG 数据...")

    # 初始化数据
    stats = initialize_from_files(
        semantic_rules_path="data/semantic_rules.json",
        sql_examples_path="data/sql_examples.json",
    )

    print(f"✓ 初始化完成:")
    print(f"  - 语义规则: {stats['semantic_rules']} 条")
    print(f"  - SQL 示例: {stats['sql_examples']} 条")
    print(f"\n数据已存储到: {settings.RAG_PERSIST_DIR}")


if __name__ == "__main__":
    main()
