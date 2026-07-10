"""
AGENT_SYSTEM_PROMPT 单元测试 — 查询偏好段落验证

测试覆盖：
- 查询偏好段落存在于 AGENT_SYSTEM_PROMPT 中
- 段落包含所有必需的使用规则
- 段落在长期记忆段落之后
"""

from app.agent.prompts import AGENT_SYSTEM_PROMPT


class TestAgentSystemPromptPreferences:
    """测试 AGENT_SYSTEM_PROMPT 中查询偏好段落（需求 4.2）"""

    def test_prompt_contains_preference_section(self):
        """AGENT_SYSTEM_PROMPT 应包含 '查询偏好' 段落标题"""
        assert "## 查询偏好" in AGENT_SYSTEM_PROMPT

    def test_preference_section_after_long_term_memory(self):
        """查询偏好段落应在长期记忆段落之后"""
        long_term_idx = AGENT_SYSTEM_PROMPT.find("## 长期记忆")
        pref_idx = AGENT_SYSTEM_PROMPT.find("## 查询偏好")
        assert long_term_idx >= 0, "应有长期记忆段落"
        assert pref_idx >= 0, "应有查询偏好段落"
        assert long_term_idx < pref_idx, (
            f"查询偏好段落应在长期记忆之后，但长期记忆在 {long_term_idx}，查询偏好在 {pref_idx}"
        )

    def test_preference_section_describes_source(self):
        """查询偏好段落应说明信息来源（自动记录的成功查询）"""
        assert "自动记录" in AGENT_SYSTEM_PROMPT
        assert "成功执行的 SQL 查询" in AGENT_SYSTEM_PROMPT

    def test_preference_section_describes_content(self):
        """查询偏好段落应说明内容（表名、数据库名、查询次数）"""
        assert "表名" in AGENT_SYSTEM_PROMPT
        assert "数据库名" in AGENT_SYSTEM_PROMPT
        assert "查询次数" in AGENT_SYSTEM_PROMPT

    def test_preference_section_describes_difference_from_long_term_memory(self):
        """查询偏好段落应说明与长期记忆的区别"""
        assert "长期记忆是概括性的操作描述" in AGENT_SYSTEM_PROMPT
        assert "偏好信息是精确的技术元数据" in AGENT_SYSTEM_PROMPT

    def test_preference_usage_rule_check_preference_table(self):
        """使用规则：优先检查偏好表中是否有匹配项"""
        assert "优先检查偏好表中是否有匹配项" in AGENT_SYSTEM_PROMPT

    def test_preference_usage_rule_use_schema_and_database(self):
        """使用规则：优先使用偏好表中的 schema_id 和 database_name"""
        assert "优先使用偏好表中的 schema_id" in AGENT_SYSTEM_PROMPT
        assert "database_name" in AGENT_SYSTEM_PROMPT

    def test_preference_usage_rule_natural_mention(self):
        """使用规则：在回答中自然地引用偏好信息"""
        assert "根据你之前的查询记录" in AGENT_SYSTEM_PROMPT

    def test_preference_usage_rule_auxiliary_reference(self):
        """使用规则：偏好信息是辅助参考，仍需验证"""
        assert "偏好信息是辅助参考" in AGENT_SYSTEM_PROMPT
        assert "仍需要通过 find_table 和 query_database 验证" in AGENT_SYSTEM_PROMPT

    def test_preference_section_no_duplicate(self):
        """查询偏好段落只出现一次"""
        assert AGENT_SYSTEM_PROMPT.count("## 查询偏好") == 1