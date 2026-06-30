"""
Spider 1.0 基准测试 - 评估封装

职责：
1. 封装官方 Spider evaluation.py 的 evaluate() 函数
2. 格式化输出评估结果
3. 保存结果为 JSON
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional


def evaluate_spider(
    gold_path: str,
    pred_path: str,
    db_dir: str,
    table_path: str,
    etype: str = "match",
) -> Optional[dict]:
    """
    调用 Spider 官方评估脚本

    参数：
        gold_path: gold 文件路径（每行 "SQL \t db_id"）
        pred_path: 预测文件路径（每行一条 SQL）
        db_dir: SQLite 数据库目录
        table_path: tables.json 路径
        etype: 评估类型 - "match"（精确匹配）/ "exec"（执行准确率）/ "all"（两者）

    返回：
        评估结果字典，包含各难度级别的分数；失败时返回 None
    """
    # 检查必要文件
    for path, name in [(gold_path, "gold"), (pred_path, "pred"), (table_path, "tables.json")]:
        if not Path(path).exists():
            print(f"[spider_evaluator] 错误：{name} 文件不存在: {path}")
            return None

    db_path = Path(db_dir)
    if not db_path.exists():
        print(f"[spider_evaluator] 错误：数据库目录不存在: {db_dir}")
        print(f"[spider_evaluator] 跳过执行准确率评估，仅做精确匹配评估")
        if etype == "exec":
            return None
        etype = "match"

    # 关键：将 benchmark/spider 添加到 sys.path，使 evaluation.py 可以 import process_sql
    project_root = Path(__file__).resolve().parent.parent.parent
    spider_dir = str(project_root / "benchmark" / "spider")
    if spider_dir not in sys.path:
        sys.path.insert(0, spider_dir)

    try:
        from evaluation import evaluate, build_foreign_key_map_from_json
    except ImportError as e:
        print(f"[spider_evaluator] 错误：无法导入 Spider evaluation 模块: {e}")
        print(f"[spider_evaluator] 请确保 benchmark/spider/evaluation.py 存在")
        return None

    # 构建外键映射
    try:
        kmaps = build_foreign_key_map_from_json(table_path)
    except Exception as e:
        print(f"[spider_evaluator] 警告：构建外键映射失败: {e}，使用空映射")
        kmaps = {}

    # 调用官方 evaluate() 函数
    # evaluation.py 会直接打印结果到 stdout，我们用 redirect_stdout 捕获
    print(f"\n[spider_evaluator] 开始评估 (etype={etype})...")
    print(f"[spider_evaluator] Gold: {gold_path}")
    print(f"[spider_evaluator] Pred: {pred_path}")
    print()

    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            evaluate(gold_path, pred_path, db_dir, etype, kmaps)
    except Exception as e:
        print(f"[spider_evaluator] 评估过程出错: {e}")
        # 打印已捕获的输出
        output = captured.getvalue()
        if output.strip():
            print(f"[spider_evaluator] 已捕获的输出:\n{output}")
        return None

    # 输出评估结果
    output = captured.getvalue()
    print(output)

    return {"raw_output": output}


def print_results(scores: dict | None) -> None:
    """格式化打印评估结果"""
    if scores is None:
        print("[spider_evaluator] 无评估结果")
        return

    raw = scores.get("raw_output", "")
    if raw:
        print("=" * 60)
        print(raw)
        print("=" * 60)


def save_results(scores: dict | None, output_path: str) -> None:
    """保存评估结果为 JSON 文件"""
    if scores is None:
        print("[spider_evaluator] 无评估结果可保存")
        return

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

    print(f"[spider_evaluator] 结果已保存: {out}")