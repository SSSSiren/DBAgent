"""
验证 SQL Judge 和 Quality Judge 的 LLM 调用是否正常工作。
用法: cd DBAgent && python -m tests.evaluation.verify_judge_llm
"""
import asyncio
import sys
import os

# Ensure DBAgent is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from openai import AsyncOpenAI
from app.config import get_settings


async def verify_sql_judge():
    """验证 Tier 3 (LLM) SQL 评判"""
    from tests.evaluation.judges.sql_judge import judge_sql_correctness

    settings = get_settings()
    model = settings.llm_model

    # 模拟一个 OneDBA client（不需要真实数据库连接，因为 Tier 1/2 会失败，自动进入 Tier 3）
    class FakeOneDBAClient:
        async def execute_sql(self, schema_id, sql):
            raise RuntimeError("模拟: 无真实数据库连接")

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    print("=" * 60)
    print("验证 SQL Judge (Tier 3 LLM 评判)")
    print(f"  base_url: {settings.llm_base_url}")
    print(f"  model:    {model}")
    print("=" * 60)

    result = await judge_sql_correctness(
        generated_sql="SELECT order_type, COUNT(*) AS cnt FROM order_record GROUP BY order_type ORDER BY cnt DESC",
        reference_sql="SELECT order_type, COUNT(*) AS order_count FROM order_record GROUP BY order_type ORDER BY order_count DESC;",
        schema_id=65938636,
        question="统计每种工单类型的数量，按数量降序排列",
        onedba_client=FakeOneDBAClient(),
        llm_client=client,
        model=model,
    )

    print(f"\n结果:")
    print(f"  tier:              {result.tier}")
    print(f"  passed:            {result.passed}")
    print(f"  score:             {result.score}")
    print(f"  syntax_ok:         {result.syntax_ok}")
    print(f"  diff_summary:      {result.diff_summary}")
    print(f"  llm_judge_explanation: {result.llm_judge_explanation}")

    if result.tier == 3 and result.llm_judge_explanation:
        print("\n✅ SQL Judge LLM 调用成功！")
        return True
    elif "LLM 评判失败" in (result.diff_summary or ""):
        print(f"\n❌ SQL Judge LLM 调用失败: {result.diff_summary}")
        return False
    else:
        print(f"\n⚠️  未进入 Tier 3（可能 Tier 1/2 已处理），但无 LLM 错误")
        return True


async def verify_quality_judge():
    """验证 Quality Judge"""
    from tests.evaluation.judges.quality_judge import judge_answer_quality

    settings = get_settings()
    model = settings.llm_model

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    print("\n" + "=" * 60)
    print("验证 Quality Judge (回答质量评判)")
    print(f"  base_url: {settings.llm_base_url}")
    print(f"  model:    {model}")
    print("=" * 60)

    result = await judge_answer_quality(
        question="统计每种工单类型的数量，按数量降序排列",
        agent_response="""## 工单类型统计

查询了 `order_record` 表，按工单类型分组统计数量，结果如下：

```sql
SELECT order_type, COUNT(*) AS cnt FROM order_record GROUP BY order_type ORDER BY cnt DESC
```

| 序号 | 工单类型 | 数量 |
| --- | --- | --- |
| 1 | dataChange | 364 |
| 2 | permission | 133 |

共 20 种工单类型，其中数据变更以 364 单遥遥领先。""",
        reference_sql="SELECT order_type, COUNT(*) AS order_count FROM order_record GROUP BY order_type ORDER BY order_count DESC;",
        llm_client=client,
        model=model,
    )

    print(f"\n结果:")
    print(f"  score:             {result.score}")
    print(f"  completeness:      {result.completeness}")
    print(f"  accuracy:          {result.accuracy}")
    print(f"  clarity:           {result.clarity}")
    print(f"  sql_transparency:  {result.sql_transparency}")
    print(f"  explanation:       {result.explanation}")

    if "LLM 评判失败" in (result.explanation or ""):
        print(f"\n❌ Quality Judge LLM 调用失败: {result.explanation}")
        return False
    elif result.score > 0:
        print(f"\n✅ Quality Judge LLM 调用成功！score={result.score:.2%}")
        return True
    else:
        print(f"\n⚠️  Quality Judge score=0，但无 LLM 错误")
        return False


async def main():
    settings = get_settings()
    if not settings.llm_api_key:
        print("❌ LLM_API_KEY 未配置，无法验证")
        sys.exit(1)

    sql_ok = await verify_sql_judge()
    quality_ok = await verify_quality_judge()

    print("\n" + "=" * 60)
    print("验证总结")
    print(f"  SQL Judge:     {'✅ 正常' if sql_ok else '❌ 失败'}")
    print(f"  Quality Judge: {'✅ 正常' if quality_ok else '❌ 失败'}")
    print("=" * 60)

    if sql_ok and quality_ok:
        print("\n🎉 两个 Judge 的 LLM 调用均正常工作！")
        sys.exit(0)
    else:
        print("\n🔧 仍有问题需要排查")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())