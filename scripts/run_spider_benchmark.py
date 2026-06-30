"""
Spider 1.0 基准测试运行器

用法：
    # 快速测试（5条，不评估，使用示例数据）
    python scripts/run_spider_benchmark.py \
        --data-dir benchmark/spider/evaluation_examples/examples \
        --limit 5 --skip-eval

    # 完整测试（需要先下载 Spider 数据集到 data/spider/）
    python scripts/run_spider_benchmark.py --data-dir data/spider

    # 仅评估已生成的预测文件
    python scripts/run_spider_benchmark.py --data-dir data/spider --skip-predict
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径上
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="Spider 1.0 Text-to-SQL 基准测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 快速测试（5条，不评估）
  python scripts/run_spider_benchmark.py \\
      --data-dir benchmark/spider/evaluation_examples/examples \\
      --limit 5 --skip-eval

  # 完整 dev 集测试
  python scripts/run_spider_benchmark.py --data-dir data/spider

  # 仅评估已有预测
  python scripts/run_spider_benchmark.py --data-dir data/spider --skip-predict
        """,
    )
    parser.add_argument(
        "--data-dir", default="data/spider",
        help="Spider 数据目录（包含 tables.json, dev.json, database/）",
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
        "--etype", default="match", choices=["match", "exec", "all"],
        help="评估类型（默认: match）。exec 需要数据库文件",
    )
    parser.add_argument(
        "--table-path", default=None,
        help="tables.json 路径（--skip-predict 时用于评估，默认: {data_dir}/tables.json）",
    )
    parser.add_argument(
        "--db-dir", default=None,
        help="数据库目录（--skip-predict 时用于评估，默认: {data_dir}/database）",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = args.output_dir or str(data_dir / "output")

    # ── 步骤 1：加载数据 + 预测 ──
    if not args.skip_predict:
        if not data_dir.exists():
            print(f"错误：数据目录不存在: {data_dir}")
            print("请从 Spider 官网下载数据集: https://yale-lily.github.io/spider")
            sys.exit(1)
        from app.benchmark.spider_loader import load_spider_data

        try:
            examples = load_spider_data(str(data_dir), args.split)
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
        from app.benchmark.spider_runner import run_spider_benchmark, write_predictions

        predictions = asyncio.run(
            run_spider_benchmark(
                examples=examples,
                max_concurrent=args.concurrent,
                limit=args.limit,
            )
        )

        pred_path, gold_path = write_predictions(predictions, examples, output_dir)
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

    from app.benchmark.spider_evaluator import evaluate_spider, print_results, save_results

    table_path = args.table_path or str(data_dir / "tables.json")
    db_dir = args.db_dir or str(data_dir / "database")

    if not Path(db_dir).exists():
        print(f"\n[main] 警告：数据库目录不存在: {db_dir}")
        print("[main] 执行准确率 (EX) 评估需要 SQLite 数据库文件")
        if args.etype in ("exec", "all"):
            print(f"[main] 将 etype 从 '{args.etype}' 降级为 'match'")
            actual_etype = "match"
        else:
            actual_etype = args.etype
    else:
        actual_etype = args.etype

    scores = evaluate_spider(gold_path, pred_path, db_dir, table_path, actual_etype)
    print_results(scores)

    results_path = str(Path(output_dir) / "results.json")
    save_results(scores, results_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())