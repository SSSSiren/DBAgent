# RAG (检索增强生成) 模块

本模块为 DBAgent 提供检索增强生成能力，通过向量检索相关文档、SQL 示例和业务知识，提升 LLM 的回答质量。

## 架构概览

```
用户查询 → Embedding 向量化 → 向量检索 → 相关文档 → 注入 Prompt → LLM 生成回答
```

## 核心组件

### 1. Embeddings (`embeddings.py`)
- 使用 OpenAI `text-embedding-3-small` 模型
- 支持批量文本向量化
- 支持查询向量化

### 2. Vector Store (`vector_store.py`)
- 基于 FAISS 的向量存储
- 支持持久化到磁盘
- 支持相似度检索

### 3. Retriever (`retriever.py`)
- 封装检索逻辑
- 支持 MMR (最大边际相关性) 检索
- 支持结果格式化

### 4. Tools (`tools.py`)
提供三个 Agent 工具：
- `search_semantic_rules`: 搜索业务语义规则
- `search_sql_examples`: 搜索 SQL 示例
- `search_documentation`: 搜索文档

## 快速开始

### 1. 安装依赖

```bash
pip install faiss-cpu
```

### 2. 配置环境变量

在 `.env` 文件中添加：

```bash
# OpenAI API 配置（用于 Embedding）
OPENAI_API_KEY=your-openai-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# RAG 配置
RAG_ENABLED=true
RAG_TOP_K=4
RAG_PERSIST_DIR=data/vector_store
EMBEDDING_MODEL=text-embedding-3-small
```

### 3. 初始化数据

运行初始化脚本，将示例数据导入向量库：

```bash
python scripts/init_rag.py
```

这会导入：
- 5 条语义规则（有效订单、GMV 等）
- 5 条 SQL 示例

### 4. 使用 RAG 工具

Agent 现在可以自动调用 RAG 工具：

```
用户：什么是有效订单？

Agent 思考：用户询问业务概念，应该搜索语义规则
→ 调用 search_semantic_rules("有效订单")
→ 返回：有效订单定义：paid 和 completed 订单才计入有效订单
→ 生成回答
```

## 添加自定义数据

### 添加语义规则

编辑 `data/semantic_rules.json`：

```json
{
  "rules": [
    {
      "name": "规则名称",
      "description": "规则描述",
      "sql": "SQL 片段",
      "tables": ["表名"],
      "domain": "业务域"
    }
  ]
}
```

### 添加 SQL 示例

编辑 `data/sql_examples.json`：

```json
[
  {
    "question": "用户问题",
    "sql": "SQL 查询语句",
    "tables": ["表名"],
    "description": "说明"
  }
]
```

### 重新初始化

修改数据后，重新运行：

```bash
python scripts/init_rag.py
```

## 编程接口

### 直接使用 Retriever

```python
from app.rag import Retriever

# 创建检索器
retriever = Retriever("semantic_rules")

# 检索相关文档
docs = retriever.retrieve("什么是有效订单", k=3)

# 格式化结果
context = retriever.format_as_context(docs)
print(context)
```

### 批量添加文档

```python
from langchain_core.documents import Document
from app.rag import Retriever

retriever = Retriever("my_collection")

# 添加文档
docs = [
    Document(
        page_content="文档内容",
        metadata={"source": "manual", "tag": "business"}
    )
]
retriever.add_documents(docs)
```

### 带过滤的检索

```python
# 只检索特定表的规则
docs = retriever.retrieve(
    "订单相关规则",
    k=5,
    filter={"tables": "orders"}
)
```

## 向量库管理

### 查看统计信息

```python
from app.rag import Retriever

retriever = Retriever("semantic_rules")
stats = retriever.get_stats()
print(f"文档数量: {stats['count']}")
```

### 清空向量库

```python
retriever.vector_store.clear()
```

## 故障排查

### 问题：FAISS 未安装

```bash
pip install faiss-cpu
```

### 问题：OpenAI API Key 未配置

确保 `.env` 文件中包含：
```bash
OPENAI_API_KEY=your-key-here
```

### 问题：检索结果为空

1. 检查是否已运行初始化脚本
2. 检查向量库目录是否存在：`data/vector_store/`
3. 查看统计信息确认文档数量

### 问题：检索结果不相关

1. 增加 `RAG_TOP_K` 值
2. 检查文档内容质量
3. 考虑使用 MMR 检索提高多样性

## 性能优化

### 1. 批量 Embedding

```python
from app.rag.embeddings import embed_texts

# 批量处理，减少 API 调用
texts = ["文本1", "文本2", "文本3"]
vectors = await embed_texts(texts)
```

### 2. 缓存 Embedding

对于静态文档，可以预计算向量并缓存：

```python
import pickle
from app.rag.embeddings import embed_texts

# 预计算并保存
vectors = await embed_texts(texts)
with open("cached_vectors.pkl", "wb") as f:
    pickle.dump(vectors, f)
```

### 3. 使用本地 Embedding 模型

如果不想依赖 OpenAI API，可以使用本地模型：

```python
# 修改 embeddings.py
from langchain_community.embeddings import HuggingFaceEmbeddings

def get_embedding_model():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
```

## 下一步

- [ ] 添加更多业务规则
- [ ] 集成表结构文档
- [ ] 实现自动学习机制（从用户反馈中学习）
- [ ] 添加 RAG 效果评估工具
