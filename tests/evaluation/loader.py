"""
测试用例加载器 — 从 Markdown 文件解析 TestCase 对象
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Difficulty, TestCase


# 难度映射表（从评分汇总表提取）
_DIFFICULTY_MAP: dict[str, Difficulty] = {
    "TC-001": Difficulty.EASY, "TC-002": Difficulty.EASY, "TC-003": Difficulty.EASY,
    "TC-004": Difficulty.EASY, "TC-005": Difficulty.MEDIUM, "TC-006": Difficulty.MEDIUM,
    "TC-007": Difficulty.EASY, "TC-008": Difficulty.EASY, "TC-009": Difficulty.MEDIUM,
    "TC-010": Difficulty.MEDIUM, "TC-011": Difficulty.MEDIUM, "TC-012": Difficulty.MEDIUM,
    "TC-013": Difficulty.MEDIUM, "TC-014": Difficulty.MEDIUM, "TC-015": Difficulty.MEDIUM,
    "TC-016": Difficulty.MEDIUM, "TC-017": Difficulty.EASY, "TC-018": Difficulty.EASY,
    "TC-019": Difficulty.MEDIUM, "TC-020": Difficulty.MEDIUM, "TC-021": Difficulty.EASY,
    "TC-022": Difficulty.EASY, "TC-023": Difficulty.MEDIUM, "TC-024": Difficulty.MEDIUM,
    "TC-025": Difficulty.MEDIUM, "TC-026": Difficulty.HARD, "TC-027": Difficulty.HARD,
    "TC-028": Difficulty.HARD, "TC-029": Difficulty.HARD, "TC-030": Difficulty.HARD,
    # dw_onedba_cs 测试用例
    "CS-001": Difficulty.EASY, "CS-002": Difficulty.EASY, "CS-003": Difficulty.EASY,
    "CS-004": Difficulty.EASY, "CS-005": Difficulty.EASY, "CS-006": Difficulty.EASY,
    "CS-007": Difficulty.MEDIUM, "CS-008": Difficulty.MEDIUM, "CS-009": Difficulty.MEDIUM,
    "CS-010": Difficulty.HARD, "CS-011": Difficulty.HARD, "CS-012": Difficulty.MEDIUM,
    "CS-013": Difficulty.EASY, "CS-014": Difficulty.EASY, "CS-015": Difficulty.EASY,
    "CS-016": Difficulty.MEDIUM, "CS-017": Difficulty.MEDIUM, "CS-018": Difficulty.HARD,
    "CS-019": Difficulty.MEDIUM, "CS-020": Difficulty.MEDIUM,
}

# 类别映射表（从评分汇总表提取）
_CATEGORY_MAP: dict[str, str] = {
    "TC-001": "单表过滤", "TC-002": "单表过滤", "TC-003": "聚合",
    "TC-004": "聚合", "TC-005": "时间窗口", "TC-006": "时间窗口",
    "TC-007": "单表过滤", "TC-008": "聚合", "TC-009": "聚合",
    "TC-010": "时间窗口", "TC-011": "多条件过滤", "TC-012": "聚合",
    "TC-013": "聚合", "TC-014": "时间窗口", "TC-015": "多条件过滤",
    "TC-016": "排名", "TC-017": "单表过滤", "TC-018": "聚合",
    "TC-019": "聚合", "TC-020": "时间窗口", "TC-021": "单表过滤",
    "TC-022": "聚合", "TC-023": "JOIN", "TC-024": "JOIN",
    "TC-025": "子查询", "TC-026": "窗口函数", "TC-027": "派生指标",
    "TC-028": "时间窗口", "TC-029": "复合查询", "TC-030": "复合查询",
    # dw_onedba_cs 测试用例
    "CS-001": "单表过滤", "CS-002": "单表过滤", "CS-003": "聚合",
    "CS-004": "聚合", "CS-005": "聚合", "CS-006": "聚合",
    "CS-007": "多条件过滤", "CS-008": "时间窗口", "CS-009": "去重查询",
    "CS-010": "窗口函数", "CS-011": "派生指标", "CS-012": "复合查询",
    "CS-013": "单表过滤", "CS-014": "单表过滤", "CS-015": "聚合",
    "CS-016": "聚合", "CS-017": "多条件过滤", "CS-018": "派生指标",
    "CS-019": "时间窗口", "CS-020": "复合查询",
}

# 表名映射
_TABLE_MAP: dict[str, list[str]] = {
    "TC-001": ["order_record"], "TC-002": ["order_record"], "TC-003": ["order_record"],
    "TC-004": ["order_record"], "TC-005": ["order_record"], "TC-006": ["order_record"],
    "TC-007": ["db_alert_history"], "TC-008": ["db_alert_history"],
    "TC-009": ["db_alert_history"], "TC-010": ["db_alert_history"],
    "TC-011": ["db_alert_history"], "TC-012": ["db_alert_history"],
    "TC-013": ["effect_dba_domain_cost_v2"], "TC-014": ["effect_dba_domain_cost_v2"],
    "TC-015": ["effect_dba_domain_cost_v2"], "TC-016": ["effect_dba_domain_cost_v2"],
    "TC-017": ["effect_daily_work_v2"], "TC-018": ["effect_daily_work_v2"],
    "TC-019": ["order_audit_record"], "TC-020": ["order_audit_record"],
    "TC-021": ["account"], "TC-022": ["account"],
    "TC-023": ["order_record", "account"], "TC-024": ["order_record", "workflow_instance"],
    "TC-025": ["db_alert_history"], "TC-026": ["db_alert_history"],
    "TC-027": ["order_record"], "TC-028": ["db_alert_history"],
    "TC-029": ["db_alert_history"], "TC-030": ["order_record"],
    # dw_onedba_cs 测试用例
    "CS-001": ["db_alert_history"], "CS-002": ["db_alert_history"],
    "CS-003": ["db_alert_history"], "CS-004": ["db_alert_history"],
    "CS-005": ["db_alert_history"], "CS-006": ["db_alert_history"],
    "CS-007": ["db_alert_history"], "CS-008": ["db_alert_history"],
    "CS-009": ["db_alert_history"], "CS-010": ["db_alert_history"],
    "CS-011": ["db_alert_history"], "CS-012": ["db_alert_history"],
    "CS-013": ["todo_record_detail"], "CS-014": ["todo_record_detail"],
    "CS-015": ["todo_record_detail"], "CS-016": ["todo_record_detail"],
    "CS-017": ["todo_record_detail"], "CS-018": ["todo_record_detail"],
    "CS-019": ["todo_record_detail"], "CS-020": ["db_alert_history"],
}


def _extract_code_block(text: str) -> str:
    """从 Markdown 代码块中提取内容"""
    match = re.search(r"```(?:sql)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_expected_row_count(text: str) -> int | None:
    """从预期结果文本中提取行数"""
    # 匹配 "应返回 N 行" 或 "应返回 N 条" 或 "应返回 N"
    match = re.search(r"应返回\s*(\d+)\s*(?:[行条]|条记录)", text)
    if match:
        return int(match.group(1))
    # 匹配 "应返回 N 行" 或单纯的 "应返回 N"（没有任何量词）
    match = re.search(r"应返回\s*(\d+)", text)
    if match:
        # 确保后面没有量词冲突（非行/条/条记录）
        after = text[match.end():].strip()
        return int(match.group(1))
    return None


def _extract_judging_criteria(text: str) -> list[str]:
    """从评判要点文本中提取列表"""
    criteria: list[str] = []
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        # 匹配 "- 必须..." 或 "- **必须...**"
        if line.startswith("- "):
            criteria.append(line[2:].strip())
    return criteria


def _parse_quick_copy_section(content: str) -> dict[str, str]:
    """解析快速复制区，返回 {case_id: sql} 映射"""
    result: dict[str, str] = {}
    # 按 ### TC-XXX 或 ### CS-XXX 分割
    sections = re.split(r"### (TC-\d{3}|CS-\d{3})", content)
    # sections[0] 是快速复制区标题，后续是 [id1, body1, id2, body2, ...]
    for i in range(1, len(sections), 2):
        if i + 1 >= len(sections):
            break
        case_id = sections[i].strip()
        body = sections[i + 1]

        # 提取参考SQL
        sql_match = re.search(r"参考SQL：\s*\n```sql\s*\n?(.*?)```", body, re.DOTALL)
        if sql_match:
            result[case_id] = sql_match.group(1).strip()
    return result


def load_test_cases(markdown_path: str | None = None) -> list[TestCase]:
    """
    从 Markdown 文件加载测试用例。

    Args:
        markdown_path: Markdown 文件路径，默认为 tests/test_cases_onedba_evaluation.md

    Returns:
        TestCase 对象列表
    """
    if markdown_path is None:
        markdown_path = str(
            Path(__file__).resolve().parent.parent / "docs" / "test_cases_onedba_evaluation.md"
        )

    with open(markdown_path, encoding="utf-8") as f:
        content = f.read()

    # 分离主评测区和快速复制区
    quick_copy_start = content.find("## 快速复制区")
    main_content = content[:quick_copy_start] if quick_copy_start > 0 else content
    quick_copy_content = content[quick_copy_start:] if quick_copy_start > 0 else ""

    # 解析快速复制区的 SQL（作为备用）
    quick_sqls = _parse_quick_copy_section(quick_copy_content)

    cases: list[TestCase] = []

    # 按 ### TC-XXX 分割主内容
    # 先找到所有 TC- 标题的位置
    pattern = r"### (TC-\d{3}|CS-\d{3})\b"
    splits = list(re.finditer(pattern, main_content))

    for i, match in enumerate(splits):
        case_id = match.group(1)
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(main_content)
        section = main_content[start:end]

        # 提取自然语言问题
        question = ""
        q_match = re.search(r"\*\*自然语言问题：?\*\*\s*\n```\s*\n?(.*?)```", section, re.DOTALL)
        if q_match:
            question = q_match.group(1).strip()

        # 提取参考 SQL
        reference_sql = ""
        sql_match = re.search(r"\*\*参考答案 SQL[：:]\*\*\s*\n```sql\s*\n?(.*?)```", section, re.DOTALL)
        if sql_match:
            reference_sql = sql_match.group(1).strip()
        # 备用：从快速复制区提取
        if not reference_sql and case_id in quick_sqls:
            reference_sql = quick_sqls[case_id]

        # 提取预期结果行数
        expected_row_count = _extract_expected_row_count(section)

        # 提取评判要点
        judging_criteria: list[str] = []
        j_match = re.search(r"\*\*评判要点[：:]\*\*\s*\n(.*?)(?=\n\n|\n###|\n\*\*|\Z)", section, re.DOTALL)
        if j_match:
            judging_criteria = _extract_judging_criteria(j_match.group(1))

        difficulty = _DIFFICULTY_MAP.get(case_id, Difficulty.MEDIUM)
        category = _CATEGORY_MAP.get(case_id, "")
        tables = _TABLE_MAP.get(case_id, [])

        cases.append(TestCase(
            case_id=case_id,
            difficulty=difficulty,
            question=question,
            reference_sql=reference_sql,
            expected_row_count=expected_row_count,
            category=category,
            tables=tables,
            judging_criteria=judging_criteria,
        ))

    return cases


def filter_test_cases(
    cases: list[TestCase],
    ids: list[str] | None = None,
    difficulty: str | None = None,
    category: str | None = None,
) -> list[TestCase]:
    """
    按条件筛选测试用例。

    Args:
        cases: 所有测试用例
        ids: 按 ID 筛选（如 ["TC-001", "TC-005"]）
        difficulty: 按难度筛选（Easy/Medium/Hard）
        category: 按类别筛选

    Returns:
        筛选后的 TestCase 列表
    """
    result = cases
    if ids:
        id_set = set(ids)
        result = [c for c in result if c.case_id in id_set]
    if difficulty:
        result = [c for c in result if c.difficulty.value == difficulty]
    if category:
        result = [c for c in result if c.category == category]
    return result