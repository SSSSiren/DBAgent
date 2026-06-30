"""
BIRD 基准测试 - 核心运行器

职责：
1. 遍历 BIRD 测试用例，并发调用 LLM 生成 SQL
2. 从 LLM 响应中提取 SQL 语句
3. 写预测文件和 gold 文件（BIRD 格式：SQL \\t----- bird -----\\t db_id）

与 Spider 的差异：
- 预测文件格式不同（BIRD 使用 \\t----- bird -----\\t 分隔符）
- 支持 evidence 字段（可选传入）
"""

import asyncio
import re
import time
from pathlib import Path

from app.agent.llm import get_llm
from app.benchmark.bird_loader import BirdExample
from app.benchmark.bird_prompt import build_prompt


def extract_sql_from_response(response: str) -> str:
    """
    从 LLM 响应中提取 SQL 语句

    与 Spider 用相同的提取逻辑（三层回退策略）：
    1. 提取 ```sql ... ``` 代码块
    2. 查找以 SELECT/WITH 开头的 SQL 语句
    3. 返回原始响应
    """
    response = response.strip()

    # 策略1：提取 ```sql ... ``` 代码块
    sql_match = re.search(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    # 策略1b：提取 ``` ... ``` 代码块（无语言标记）
    code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
        if re.search(r'\b(SELECT|WITH)\b', code, re.IGNORECASE):
            return code

    # 策略2：查找以 SELECT/WITH 开头的 SQL 语句
    sql_match = re.search(
        r'\b(SELECT|WITH)\b.+?(?:;|$)', response, re.DOTALL | re.IGNORECASE
    )
    if sql_match:
        return sql_match.group(0).strip().rstrip(";")

    # 策略3：返回原始响应
    if "SQL:" in response:
        after_sql = response.split("SQL:")[-1].strip()
        return after_sql

    return response


async def generate_single_sql(
    example: BirdExample,
    include_evidence: bool = True,
) -> tuple[str, str]:
    """
    为单个 BIRD 示例生成 SQL

    参数：
        example: BirdExample 实例
        include_evidence: 是否在 prompt 中包含 evidence

    返回：
        (predicted_sql, error_message)
    """
    prompt = build_prompt(example, include_evidence=include_evidence)
    try:
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        sql = extract_sql_from_response(str(response.content))
        return sql, ""
    except Exception as e:
        return "", str(e)


async def run_bird_benchmark(
    examples: list[BirdExample],
    max_concurrent: int = 5,
    limit: int = 0,
    include_evidence: bool = True,
) -> list[tuple[str, str, str, str]]:
    """
    运行 BIRD 基准测试（LLM 模式）

    参数：
        examples: 测试用例列表
        max_concurrent: 最大并发 LLM 调用数
        limit: 最大测试条数（0 = 全部）
        include_evidence: 是否在 prompt 中包含 evidence

    返回：
        [(predicted_sql, gold_sql, db_id, error_message), ...]
    """
    if limit > 0:
        examples = examples[:limit]

    total = len(examples)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_one(idx: int, example: BirdExample) -> tuple[int, str, str, str, str, float]:
        async with semaphore:
            start = time.time()
            pred_sql, error = await generate_single_sql(example, include_evidence)
            elapsed = time.time() - start
            return idx, pred_sql, example.gold_sql, example.db_id, error, elapsed

    tasks = [run_one(i, ex) for i, ex in enumerate(examples)]

    results: list[tuple[str, str, str, str]] = []
    success_count = 0
    fail_count = 0
    total_time = 0.0

    print(f"\n[bird_runner] 开始运行 {total} 条测试用例 (并发={max_concurrent}, evidence={include_evidence})...\n")

    for coro in asyncio.as_completed(tasks):
        try:
            idx, pred_sql, gold_sql, db_id, error, elapsed = await coro
        except Exception as e:
            print(f"  [ERROR] 任务异常: {e}")
            fail_count += 1
            continue

        results.append((pred_sql, gold_sql, db_id, error))
        total_time += elapsed

        if error:
            fail_count += 1
        else:
            success_count += 1

        done = success_count + fail_count
        avg_time = total_time / done if done > 0 else 0

        if done % 10 == 0 or done == total:
            status = "✓" if not error else f"✗ ({error[:40]})"
            print(
                f"  [{done}/{total}] {status}  "
                f"成功:{success_count} 失败:{fail_count}  "
                f"耗时:{elapsed:.1f}s 平均:{avg_time:.1f}s"
            )

    print(f"\n[bird_runner] 完成: {success_count}/{total} 成功, {fail_count}/{total} 失败")
    print(f"[bird_runner] 总耗时: {total_time:.1f}s, 平均: {total_time/total:.1f}s/条")

    return results


def write_predictions(
    predictions: list[tuple[str, str, str, str]],  # [(pred_sql, gold_sql, db_id, error), ...]
    output_dir: str,
) -> tuple[str, str]:
    """
    写入 BIRD 格式的预测文件和 gold 文件

    BIRD 格式（与 Spider 不同）：
      pred.txt: 每行 "predicted SQL \\t----- bird -----\\t db_id"
      gold.txt: 每行 "gold SQL \\t----- bird -----\\t db_id"

    返回：
        (pred_path, gold_path)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pred_path = out / "pred.txt"
    gold_path = out / "gold.txt"

    BIRD_SEP = "\t----- bird -----\t"

    with open(pred_path, "w", encoding="utf-8") as pf, \
         open(gold_path, "w", encoding="utf-8") as gf:
        for pred_sql, gold_sql, db_id, error in predictions:
            pred_sql_clean = " ".join(pred_sql.strip().split())
            gold_sql_clean = " ".join(gold_sql.strip().split())

            pf.write(f"{pred_sql_clean}{BIRD_SEP}{db_id}\n")
            gf.write(f"{gold_sql_clean}{BIRD_SEP}{db_id}\n")

    print(f"[bird_runner] 预测文件: {pred_path} ({pred_path.stat().st_size} bytes)")
    print(f"[bird_runner] Gold 文件: {gold_path} ({gold_path.stat().st_size} bytes)")

    return str(pred_path), str(gold_path)