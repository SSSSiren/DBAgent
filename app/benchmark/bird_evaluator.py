"""
BIRD 基准测试 - 评估模块

职责：
1. 实现 BIRD 的执行准确率（EX）评估
2. 实现效率评分（VES）评估
3. 格式化输出和保存结果

BIRD 评估指标：
- EX (Execution Accuracy)：预测 SQL 执行结果与黄金 SQL 结果一致
- VES (Valid Efficiency Score)：在 EX 基础上乘以效率系数
- Soft F1：基于 SQL 子句的软匹配

与 Spider 的差异：
- BIRD 使用自己的评估体系，不依赖 Spider 的 evaluation.py
- 需要 SQLite 数据库文件来执行 SQL 并比较结果
- VES 需要测量执行时间
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


def _execute_sql(sql: str, db_path: str, timeout: float = 30.0) -> tuple[Optional[list], float, Optional[str]]:
    """
    在 SQLite 数据库上执行 SQL

    返回：
        (result_rows, execution_time, error_message)
        成功时 result_rows 为结果列表，error_message 为 None
        失败时 result_rows 为 None，error_message 为错误信息
    """
    if not Path(db_path).exists():
        return None, 0.0, f"数据库文件不存在: {db_path}"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = lambda cursor, row: row
        cursor = conn.cursor()

        start = time.perf_counter()
        cursor.execute(sql)
        rows = cursor.fetchall()
        elapsed = time.perf_counter() - start

        conn.close()
        return rows, elapsed, None
    except Exception as e:
        return None, 0.0, str(e)


def _normalize_result(rows: list) -> list:
    """标准化查询结果用于比较"""
    if not rows:
        return []
    return sorted([tuple(r) for r in rows])


def evaluate_ex(
    gold_path: str,
    pred_path: str,
    db_dir: str,
) -> dict:
    """
    执行准确率（EX）评估

    对每条预测 SQL 和黄金 SQL 分别在对应数据库上执行，比较结果集是否一致。

    参数：
        gold_path: gold 文件路径（BIRD 格式：SQL \\t----- bird -----\\t db_id）
        pred_path: pred 文件路径（BIRD 格式：SQL \\t----- bird -----\\t db_id）
        db_dir: 数据库目录（dev_databases/）

    返回：
        评估结果字典
    """
    BIRD_SEP = "\t----- bird -----\t"

    with open(gold_path, "r", encoding="utf-8") as f:
        gold_lines = [line.strip() for line in f if line.strip()]

    with open(pred_path, "r", encoding="utf-8") as f:
        pred_lines = [line.strip() for line in f if line.strip()]

    if len(gold_lines) != len(pred_lines):
        print(f"[bird_evaluator] 警告：gold({len(gold_lines)}) 和 pred({len(pred_lines)}) 行数不一致")

    total = min(len(gold_lines), len(pred_lines))
    correct = 0
    errors = 0
    details: list[dict] = []

    for i in range(total):
        gold_line = gold_lines[i]
        pred_line = pred_lines[i]

        try:
            gold_sql, gold_db_id = gold_line.rsplit(BIRD_SEP, 1)
        except ValueError:
            gold_sql = gold_line
            gold_db_id = ""

        try:
            pred_sql, pred_db_id = pred_line.rsplit(BIRD_SEP, 1)
        except ValueError:
            pred_sql = pred_line
            pred_db_id = gold_db_id

        db_path = Path(db_dir) / gold_db_id / f"{gold_db_id}.sqlite"

        gold_result, gold_time, gold_err = _execute_sql(gold_sql, str(db_path))
        pred_result, pred_time, pred_err = _execute_sql(pred_sql, str(db_path))

        is_match = False
        if gold_err is None and pred_err is None:
            is_match = _normalize_result(gold_result) == _normalize_result(pred_result)

        if is_match:
            correct += 1
        if pred_err:
            errors += 1

        details.append({
            "index": i,
            "db_id": gold_db_id,
            "pred_sql": pred_sql,
            "gold_sql": gold_sql,
            "ex_match": is_match,
            "pred_time": round(pred_time, 4),
            "gold_time": round(gold_time, 4),
            "error": pred_err,
        })

    ex_score = correct / total if total > 0 else 0.0

    return {
        "metric": "EX",
        "total": total,
        "correct": correct,
        "errors": errors,
        "score": round(ex_score, 4),
        "details": details,
    }


def evaluate_ves(
    gold_path: str,
    pred_path: str,
    db_dir: str,
) -> dict:
    """
    效率评分（VES）评估

    VES = EX × Efficiency
    其中 Efficiency 基于预测 SQL 执行时间与黄金 SQL 执行时间的比率。

    评分规则：
    - 预测 SQL 执行时间 ≤ 黄金 SQL 执行时间 → 效率分 = 1.0
    - 预测 SQL 执行时间 > 黄金 SQL 执行时间 → 效率分按比例扣减
    """
    ex_result = evaluate_ex(gold_path, pred_path, db_dir)

    total = ex_result["total"]
    ves_score = 0.0
    efficiency_sum = 0.0
    valid_count = 0

    for detail in ex_result["details"]:
        if not detail["ex_match"]:
            continue

        pred_time = detail["pred_time"]
        gold_time = detail["gold_time"]

        if gold_time <= 0:
            efficiency = 1.0
        elif pred_time <= gold_time:
            efficiency = 1.0
        else:
            # 效率按比例扣减：gold_time / pred_time
            efficiency = gold_time / pred_time
            efficiency = max(0.0, min(1.0, efficiency))

        ves_score += efficiency
        efficiency_sum += efficiency
        valid_count += 1

        detail["efficiency"] = round(efficiency, 4)

    if total > 0:
        ves_score = ves_score / total
    avg_efficiency = efficiency_sum / valid_count if valid_count > 0 else 0.0

    return {
        "metric": "VES",
        "total": total,
        "ex_score": ex_result["score"],
        "ves_score": round(ves_score, 4),
        "avg_efficiency": round(avg_efficiency, 4),
        "valid_count": valid_count,
        "details": ex_result["details"],
    }


def evaluate_bird(
    gold_path: str,
    pred_path: str,
    db_dir: str,
    metrics: str = "all",
) -> Optional[dict]:
    """
    运行 BIRD 评估

    参数：
        gold_path: gold 文件路径
        pred_path: pred 文件路径
        db_dir: 数据库目录（dev_databases/）
        metrics: 评估指标 - "ex" / "ves" / "all"

    返回：
        评估结果字典
    """
    for path, name in [(gold_path, "gold"), (pred_path, "pred")]:
        if not Path(path).exists():
            print(f"[bird_evaluator] 错误：{name} 文件不存在: {path}")
            return None

    db_path = Path(db_dir)
    if not db_path.exists():
        print(f"[bird_evaluator] 错误：数据库目录不存在: {db_dir}")
        return None

    print(f"\n[bird_evaluator] 开始评估 (metrics={metrics})...")
    print(f"[bird_evaluator] Gold: {gold_path}")
    print(f"[bird_evaluator] Pred: {pred_path}")
    print(f"[bird_evaluator] DB Dir: {db_dir}")
    print()

    results = {}

    if metrics in ("ex", "all"):
        ex_result = evaluate_ex(gold_path, pred_path, db_dir)
        results["EX"] = ex_result
        print(f"  EX (Execution Accuracy): {ex_result['score']:.2%} "
              f"({ex_result['correct']}/{ex_result['total']})")

    if metrics in ("ves", "all"):
        ves_result = evaluate_ves(gold_path, pred_path, db_dir)
        results["VES"] = ves_result
        print(f"  VES (Valid Efficiency Score): {ves_result['ves_score']:.4f} "
              f"(EX={ves_result['ex_score']:.2%}, 效率={ves_result['avg_efficiency']:.2%})")

    # 按难度分组统计
    print()

    return results


def print_results(results: dict | None) -> None:
    """格式化打印评估结果"""
    if results is None:
        print("[bird_evaluator] 无评估结果")
        return

    print("=" * 60)
    print("BIRD Benchmark Results")
    print("=" * 60)

    for metric, data in results.items():
        if metric == "EX":
            print(f"\n  EX (Execution Accuracy):")
            print(f"    Score: {data['score']:.2%}")
            print(f"    Correct: {data['correct']}/{data['total']}")
            print(f"    Errors: {data['errors']}")
        elif metric == "VES":
            print(f"\n  VES (Valid Efficiency Score):")
            print(f"    Score: {data['ves_score']:.4f}")
            print(f"    EX: {data['ex_score']:.2%}")
            print(f"    Avg Efficiency: {data['avg_efficiency']:.2%}")

    print("\n" + "=" * 60)


def save_results(results: dict | None, output_path: str) -> None:
    """保存评估结果为 JSON 文件"""
    if results is None:
        print("[bird_evaluator] 无评估结果可保存")
        return

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 去掉 details 以减小文件大小
    slim_results = {}
    for metric, data in results.items():
        slim_results[metric] = {k: v for k, v in data.items() if k != "details"}

    with open(out, "w", encoding="utf-8") as f:
        json.dump(slim_results, f, ensure_ascii=False, indent=2)

    print(f"[bird_evaluator] 结果已保存: {out}")