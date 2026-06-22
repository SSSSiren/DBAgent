意图识别问题：

当前模式：
- LLM 做通用理解
- 规则做 NL2SQL 关键槽位提取
- plan_node 根据结构化结果选择工作流
问题：
提取关键词的 NL2SQL的覆盖范围有限，当已知规则不够完善时，需要增量修补硬编码。
方案：
保留规则作为稳定兜底，但把 NL2SQL 槽位提取
  升级为“LLM 结构化解析 + schema 约束校验 + 规则修正”。




完善功能：
1. 把 NL2SQL 内部步骤展示到前端
     现在前端只看到：

     工具调用：nl2sql_query(completed)
     但真实内部其实做了：

     list_databases -> SHOW TABLES -> DESCRIBE -> generate_sql -> validate_sql -> execute_sql
     下一步应该把这些子步骤展示出来，方便开发人员信任和排查。

     下一步应该把这些子步骤展示出来，方便开发人员信任和排查。


  2. 做 session 级数据库选择
     当前如果用户不带数据库名，依赖摘要推断 dw-onedba-t1，可用但不够稳。应该让前端/后端明确保存：

     selected_schema_id
     selected_database

     用户选择一次库后，后续问题直接复用。

  3. 增加 SQL 展示区
     对开发人员来说，SQL 很重要。前端应该固定展示：
      - 生成 SQL
      - SQL 解释
      - 假设与限制
      - 查询结果

  4. 补 mock LLM 的端到端测试
     现在很多真实验证跑通了，但自动测试还偏单元。应该补：
      - 单表排行
      - Top-N
      - 多表前缀计数
      - 缺数据库上下文澄清
      - SQL 修复路径

  5. 把旧规则清理掉
     agent/nodes.py 里还残留早期的：
      - infer_sql
      - fallback_plan
      - normalize_plan
      - 针对 id/nodeid 的旧逻辑

     NL2SQL 路径稳定后，这些应该逐步删掉或隔离，避免未来又走回旧路径。