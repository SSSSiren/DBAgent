"""
BIRD 基准测试运行器

用法：
    # 快速测试（10条，不评估）
    python scripts/run_bird_benchmark.py \\
        --data-dir data/bird_mini_dev \\
        --limit 10 --skip-eval

    # 完整测试（需要先下载 BIRD 数据集到 data/bird/）
    python scripts/run_bird_benchmark.py --data-dir data/bird

    # 仅评估已生成的预测文件
    python scripts/run_bird_benchmark.py --data-dir data/bird --skip-predict

    # Agent 模式（不提供 schema 和 evidence，让 Agent 自行探索）
    python scripts/run_bird_benchmark.py --data-dir data/bird --agent-mode

    # 不包含 evidence（测试 LLM 的纯 schema 理解能力）
    python scripts/run_bird_benchmark.py --data-dir data/bird --no-evidence
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

# 确保项目根目录在 Python 路径上
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 下载帮助文本（与 bird_loader.py 保持一致）
DOWNLOAD_HELP = """
数据需要单独下载，当前目录仅含代码框架，不包含数据文件。

═══ Mini-Dev（推荐，500条，~200MB） ═══
  curl -L -o /tmp/minidev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
  unzip /tmp/minidev.zip -d data/bird_mini_dev
  # 解压后：data/bird_mini_dev/sqlite/dev_databases/ 下有 .sqlite 文件

═══ HuggingFace（Mini-Dev，500条） ═══
  pip install datasets
  python3 -c "from datasets import load_dataset; load_dataset('birdsql/bird_mini_dev', 'mini_dev_sqlite')"

═══ 完整 BIRD Dev（12,751条，33.4GB） ═══
  curl -L -o /tmp/bird_dev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip
  unzip /tmp/bird_dev.zip -d data/bird
  # 解压后：data/bird/dev_databases/ 下有 .sqlite 文件和 database_description/ 目录
"""


def _find_db_dir_for_eval(data_dir: Path, split: str) -> Optional[Path]:
    """查找评估用的数据库目录（与 loader 的 _find_db_dir 保持一致）"""
    if split == "dev":
        candidates = [
            data_dir / "dev_databases",
            data_dir / "sqlite" / "dev_databases",
            data_dir / "databases",
        ]
    elif split == "train":
        candidates = [
            data_dir / "train_databases",
            data_dir / "databases",
        ]
    for path in candidates:
        if path.exists():
            return path
    return None


def main():
    parser = argparse.ArgumentParser(
        description="BIRD Text-to-SQL 基准测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 快速测试（10条，不评估）
  python scripts/run_bird_benchmark.py \\
      --data-dir data/bird_mini_dev \\
      --limit 10 --skip-eval

  # 完整 dev 集测试（LLM 模式，含 evidence）
  python scripts/run_bird_benchmark.py --data-dir data/bird

  # 不包含 evidence（测试 LLM 的纯 schema 理解能力）
  python scripts/run_bird_benchmark.py --data-dir data/bird --no-evidence

  # 仅评估已有预测
  python scripts/run_bird_benchmark.py --data-dir data/bird --skip-predict

  # VES 效率评估（需要数据库文件）
  python scripts/run_bird_benchmark.py --data-dir data/bird --metrics ves
        """,
    )
    parser.add_argument(
        "--data-dir", default="data/bird",
        help="BIRD 数据目录（包含 dev.json/train.json, dev_databases/）",
    )
    parser.add_argument(
        "--split", default="dev", choices=["dev", "train"],
        help="数据集分割（默认: dev）",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="限制测试条数（0=全部）",
    )
    parser.add_argument(
        "--concurrent", type=int, default=5,
        help="最大并发 LLM 调用数（默认: 5）",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="输出目录（默认: {data_dir}/output）",
    )
    parser.add_argument(
        "--skip-predict", action="store_true",
        help="跳过预测，仅评估已有预测文件",
    )
    parser.add_argument(
        "--skip-eval", action="store_true",
        help="跳过评估，仅生成预测文件",
    )
    parser.add_argument(
        "--no-evidence", action="store_true",
        help="不在 prompt 中包含 evidence（测试 LLM 的纯 schema 理解能力）",
    )
    parser.add_argument(
        "--agent-mode", action="store_true",
        help="Agent 模式：不提供 schema 和 evidence，Agent 自行探索数据库",
    )
    parser.add_argument(
        "--metrics", default="ex", choices=["ex", "ves", "all"],
        help="评估指标（默认: ex）。ves 需要数据库文件",
    )
    parser.add_argument(
        "--db-dir", default=None,
        help="数据库目录（--skip-predict 时用于评估，默认: {data_dir}/dev_databases）",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = args.output_dir or str(data_dir / "output")

    # ── 步骤 1：加载数据 + 预测 ──
    if not args.skip_predict:
        if not data_dir.exists():
            print(f"错误：数据目录不存在: {data_dir}")
            print(DOWNLOAD_HELP)
            sys.exit(1)

        from app.benchmark.bird_loader import load_bird_data

        try:
            # Agent 模式不加载 schema（让 Agent 自行探索）
            include_schema = not args.agent_mode
            examples = load_bird_data(str(data_dir), args.split, include_schema=include_schema)
        except FileNotFoundError as e:
            print(f"错误：{e}")
            sys.exit(1)

        if args.limit > 0:
            examples = examples[:args.limit]
            print(f"[main] 限制测试条数: {args.limit}")

        if len(examples) == 0:
            print("错误：没有可用的测试数据")
            sys.exit(1)

        # ── 步骤 2：运行 LLM 预测 ──
        from app.benchmark.bird_runner import run_bird_benchmark, write_predictions

        include_evidence = not args.no_evidence and not args.agent_mode

        print(f"[main] 模式: {'Agent (自行探索)' if args.agent_mode else 'LLM'}")
        print(f"[main] Evidence: {'包含' if include_evidence else '不包含'}")
        print(f"[main] 数据量: {len(examples)} 条")

        predictions = asyncio.run(
            run_bird_benchmark(
                examples=examples,
                max_concurrent=args.concurrent,
                limit=args.limit,
                include_evidence=include_evidence,
            )
        )

        pred_path, gold_path = write_predictions(predictions, output_dir)
    else:
        pred_path = str(Path(output_dir) / "pred.txt")
        gold_path = str(Path(output_dir) / "gold.txt")
        if not Path(pred_path).exists():
            print(f"错误：预测文件不存在: {pred_path}")
            sys.exit(1)
        if not Path(gold_path).exists():
            print(f"错误：Gold 文件不存在: {gold_path}")
            sys.exit(1)
        print(f"[main] 跳过预测，使用已有文件: {pred_path}")

    # ── 步骤 3：评估 ──
    if args.skip_eval:
        print("[main] 跳过评估")
        print(f"[main] 预测文件: {pred_path}")
        print(f"[main] Gold 文件: {gold_path}")
        return 0

    from app.benchmark.bird_evaluator import evaluate_bird, print_results, save_results

    # 评估用数据库目录：优先使用 --db-dir，其次自动探测
    if args.db_dir:
        db_dir = args.db_dir
    else:
        found = _find_db_dir_for_eval(data_dir, args.split)
        db_dir = str(found) if found else str(data_dir / f"{args.split}_databases")

    if not Path(db_dir).exists():
        # 尝试 sqlite/dev_databases（Mini-Dev 结构）
        alt_db = _find_db_dir_for_eval(data_dir, args.split)
        if alt_db:
            db_dir = str(alt_db)
        elif args.metrics in ("ves", "all"):
            print(f"\n[main] 警告：数据库目录不存在: {db_dir}")
            print("[main] VES 评估需要 SQLite 数据库文件")
            print("[main] 将 metrics 从 '{}' 降级为 'ex'".format(args.metrics))
            actual_metrics = "ex"
        else:
            actual_metrics = args.metrics
    else:
        actual_metrics = args.metrics

    results = evaluate_bird(gold_path, pred_path, db_dir, actual_metrics)
    print_results(results)

    results_path = str(Path(output_dir) / "results.json")
    save_results(results, results_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())