"""
Spider 1.0 基准测试 - 核心运行器

职责：
1. 遍历 Spider 测试用例，并发调用 LLM 生成 SQL
2. 从 LLM 响应中提取 SQL 语句
3. 写预测文件和 gold 文件
"""

import asyncio
import re
import time
from pathlib import Path

from app.agent.llm import get_llm
from app.benchmark.spider_loader import SpiderExample
from app.benchmark.spider_prompt import build_prompt


def extract_sql_from_response(response: str) -> str:
    """
    从 LLM 响应中提取 SQL 语句

    三层回退策略：
    1. 提取 ```sql ... ``` 代码块
    2. 查找以 SELECT/WITH 开头的行到分号或结尾
    3. 返回原始响应（trim 后）

    后处理：清理 Spider 解析器不兼容的语法（AS 别名、末尾分号等）
    """
    response = response.strip()

    # 策略1：提取 ```sql ... ``` 代码块
    sql_match = re.search(r'```sql\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        sql = sql_match.group(1).strip()
    else:
        # 策略1b：提取 ``` ... ``` 代码块（无语言标记）
        code_match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
            if re.search(r'\b(SELECT|WITH)\b', code, re.IGNORECASE):
                sql = code
            else:
                sql = response
        else:
            # 策略2：查找以 SELECT/WITH 开头的 SQL 语句
            sql_match = re.search(
                r'\b(SELECT|WITH)\b.+?(?:;|$)', response, re.DOTALL | re.IGNORECASE
            )
            if sql_match:
                sql = sql_match.group(0).strip()
            else:
                # 策略3：返回原始响应，移除 "SQL:" 前缀
                if "SQL:" in response:
                    sql = response.split("SQL:")[-1].strip()
                else:
                    sql = response

    # ── 后处理：清理 Spider 解析器不兼容的语法 ──
    # 1. 去掉末尾分号
    sql = sql.rstrip().rstrip(";").strip()
    # 2. 去掉列别名 AS xxx（Spider process_sql 解析器对 AS 支持不稳定）
    #    匹配模式: "AS identifier" 在 SELECT 列或聚合函数后
    #    注意：不处理字符串内的 AS、FROM 子句中的表别名
    sql = _remove_column_aliases(sql)
    # 3. 合并多余空白
    sql = " ".join(sql.split())

    return sql


def _remove_column_aliases(sql: str) -> str:
    """
    移除 SELECT 子句中的列别名 (AS xxx)，
    避免 Spider process_sql 解析器因不支持 AS 而产生假阴性。

    策略：只处理 SELECT 和 FROM 之间的部分。
    """
    # 找到 SELECT ... FROM 之间的部分
    select_match = re.match(
        r'(SELECT\s+)(.*?)(\s+FROM\s+.+)', sql, re.IGNORECASE | re.DOTALL
    )
    if not select_match:
        return sql

    prefix = select_match.group(1)   # "SELECT "
    columns_part = select_match.group(2)  # 列列表
    suffix = select_match.group(3)   # " FROM ..."

    # 按逗号分割列（小心括号内的逗号，如函数参数）
    # 简化处理：直接对 columns_part 做 AS 替换
    # 匹配 "expr AS alias" 模式，alias 是标识符，同时清理多余空格
    cleaned = re.sub(
        r'\s*\bAS\s+["\']?(\w+)["\']?', '', columns_part, flags=re.IGNORECASE
    )
    # 也处理没有 AS 关键字但有别名的简单情况（表达式后跟标识符）
    # 这一步比较危险，暂时跳过，主要靠 AS 去除

    return prefix + cleaned + suffix


async def generate_single_sql(example: SpiderExample) -> tuple[str, str]:
    """
    为单个示例生成 SQL

    返回：
        (predicted_sql, error_message)
        成功时 error_message 为空字符串
    """
    prompt = build_prompt(example)
    try:
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        sql = extract_sql_from_response(str(response.content))
        return sql, ""
    except Exception as e:
        return "", str(e)


async def run_spider_benchmark(
    examples: list[SpiderExample],
    max_concurrent: int = 5,
    limit: int = 0,
) -> list[tuple[str, str, str]]:
    """
    运行 Spider 基准测试

    参数：
        examples: 测试用例列表
        max_concurrent: 最大并发 LLM 调用数
        limit: 最大测试条数（0 = 全部）

    返回：
        [(predicted_sql, gold_sql, error_message), ...]
    """
    if limit > 0:
        examples = examples[:limit]

    total = len(examples)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_one(idx: int, example: SpiderExample) -> tuple[int, str, str, str, float]:
        async with semaphore:
            start = time.time()
            pred_sql, error = await generate_single_sql(example)
            elapsed = time.time() - start
            return idx, pred_sql, example.gold_sql, error, elapsed

    tasks = [run_one(i, ex) for i, ex in enumerate(examples)]

    # 按 idx 索引收集结果，保持与 examples 的顺序一致
    indexed_results: dict[int, tuple[str, str, str]] = {}
    success_count = 0
    fail_count = 0
    total_time = 0.0

    print(f"\n[spider_runner] 开始运行 {total} 条测试用例 (并发={max_concurrent})...\n")

    for coro in asyncio.as_completed(tasks):
        try:
            idx, pred_sql, gold_sql, error, elapsed = await coro
        except Exception as e:
            print(f"  [ERROR] 任务异常: {e}")
            fail_count += 1
            continue

        indexed_results[idx] = (pred_sql, gold_sql, error)
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

    # 按原始顺序排列结果
    results = [indexed_results[i] for i in range(total) if i in indexed_results]

    print(f"\n[spider_runner] 完成: {success_count}/{total} 成功, {fail_count}/{total} 失败")
    print(f"[spider_runner] 总耗时: {total_time:.1f}s, 平均: {total_time/total:.1f}s/条")

    return results


def write_predictions(
    predictions: list[tuple[str, str, str]],  # [(pred_sql, gold_sql, error), ...]
    examples: list[SpiderExample],
    output_dir: str,
) -> tuple[str, str]:
    """
    写入预测文件和 gold 文件

    pred.txt: 每行一条预测 SQL
    gold.txt: 每行 "gold SQL \t db_id"（Spider 评估格式）

    返回：
        (pred_path, gold_path)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pred_path = out / "pred.txt"
    gold_path = out / "gold.txt"

    with open(pred_path, "w", encoding="utf-8") as pf, \
         open(gold_path, "w", encoding="utf-8") as gf:
        for (pred_sql, gold_sql, error), example in zip(predictions, examples):
            # 预测文件：SQL 压缩为单行（Spider 评估要求每行一条 SQL）
            pred_sql_clean = " ".join(pred_sql.strip().split())
            pf.write(pred_sql_clean + "\n")
            # Gold 文件：SQL \t db_id
            gold_sql_clean = " ".join(gold_sql.strip().split())
            gf.write(f"{gold_sql_clean}\t{example.db_id}\n")

    print(f"[spider_runner] 预测文件: {pred_path} ({pred_path.stat().st_size} bytes)")
    print(f"[spider_runner] Gold 文件: {gold_path} ({gold_path.stat().st_size} bytes)")

    return str(pred_path), str(gold_path)