# DBAgent 部署教程

> 适用于单机 docker-compose 部署形态。生产推荐 K8s + 镜像仓库时，可参考本文档的配置项清单与环境变量约束。

## 一、部署前提

| 项 | 要求 |
|---|---|
| Docker | ≥ 20.10，含 `docker compose` v2 |
| 机器核数 | ≥ 2 核（gunicorn 默认 `2*CPU+1` worker，上限 8） |
| 内存 | ≥ 2GB（LLM 流式响应 + 多 worker） |
| 端口 | 默认占用 `8000`（可经 `HOST_PORT` 映射改写） |
| 网络出站 | 必须可达 LLM 网关、OneDBA 平台；按需可达 Langfuse、OpenViking |
| 数据目录 | `./data` 需可写，用于持久化 `sessions.db` |

---

## 二、配置项总览

### 必填（敏感，从环境变量/Secret 注入，禁止落文件）

| 环境变量 | 说明 |
|---|---|
| `LLM_API_KEY` | LLM 网关 API Key |
| `ONEDBA_ACCESS_TOKEN` | OneDBA 平台访问凭证 |
| `ONEDBA_ENV` | OneDBA 环境：`prd`/`test`/`uat`/`dev`/`pre` |
| `ADMIN_API_TOKEN` | Admin API Bearer token，留空则 `/api/admin/*` 返回 503 |

> compose 用 `${VAR:?...}` 约束：以上任一缺失，容器**拒绝启动**（避免裸奔上线）。

### 可选（有默认值，按需覆盖）

| 环境变量 | 默认值 | 生产建议 |
|---|---|---|
| `STORAGE_BACKEND` | `sqlite` | 保持 sqlite，持久化会话/偏好/SQL记忆/Admin 映射 |
| `LLM_EMBEDDING_PROVIDER` | `ollama` | **生产建议 `openai` 或 `auto`**，容器内无 ollama |
| `LLM_EMBEDDING_MODEL` | `text-embedding-3-small` | provider=openai/auto 时生效 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | provider=ollama/auto 回退时生效 |
| `PREFERENCE_ENABLED` | `true` | 查询偏好记忆 |
| `SQL_MEMORY_ENABLED` | `true` | SQL 历史记忆 |
| `SQL_MEMORY_SCOPE` | `user` | `user`/`database`/`mixed` |
| `HDC_ENABLED` | `true` | HDC 数据底座（依赖 OpenViking 已生成语义数据） |
| `KB_ENABLED` | `false` | OpenViking 长期对话记忆，需可达 `KB_OPENVIKING_URL` |
| `LANGFUSE_ENABLED` | `true` | LLM trace 可观测性，需配 `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` |
| `DEBUG` | `false` | 生产保持 `false` |
| `WEB_CONCURRENCY` | 自动 `2*CPU+1` | 显式指定 worker 数（**勿设空字符串**，会导致 gunicorn 启动崩溃） |
| `HOST_PORT` | `8000` | 宿主端口映射 |

---

## 三、部署步骤

### 1. 拉取代码到部署机

```bash
git clone <repo-url> dbagent
cd dbagent
```

### 2. 注入敏感配置（不落文件）

```bash
# 必填 —— 用真实值替换
export LLM_API_KEY=<your_llm_key>
export ONEDBA_ACCESS_TOKEN=<your_onedba_token>
export ONEDBA_ENV=prd
export ADMIN_API_TOKEN=$(openssl rand -hex 24)   # 生成强随机 token

# 可选 —— 可观测性
export LANGFUSE_PUBLIC_KEY=<your_langfuse_public_key>
export LANGFUSE_SECRET_KEY=<your_langfuse_secret_key>
```

> 若使用 CI/CD 或 K8s Secret，将上述变量注入部署环境即可，compose 会自动读取。

### 3. 按需覆盖非敏感默认值（可选）

```bash
# 生产建议：embedding 走 LLM 网关，避免依赖容器内不存在的 ollama
export LLM_EMBEDDING_PROVIDER=openai

# 如需固定 worker 数
export WEB_CONCURRENCY=4
```

### 4. 构建镜像并启动

```bash
docker compose build
docker compose up -d
```

### 5. 验证

```bash
# 容器状态应为 Up (healthy)
docker compose ps

# 健康检查端点
curl http://localhost:8000/health
# 期望: {"status":"ok","engine":"openai-fallback"}

# 启动日志（确认各开关生效）
docker compose logs dbagent | tail -20

# Admin API 认证（应 401 拒绝 / 200 放行）
curl -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/sql-memory/status
# 期望: 401
curl -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $ADMIN_API_TOKEN" http://localhost:8000/api/admin/sql-memory/status
# 期望: 200
```

---

## 四、运维操作

| 操作 | 命令 |
|---|---|
| 查看实时日志 | `docker compose logs -f dbagent` |
| 重启容器 | `docker compose restart` |
| gunicorn 优雅重载（不中断连接） | `docker compose kill -s HUP dbagent` |
| 停止 | `docker compose down` |
| 停止并删除数据卷（谨慎） | `docker compose down -v` |

### 升级流程

```bash
git pull
docker compose build
docker compose up -d      # 滚动重建，旧容器优雅退出
```

---

## 五、数据持久化

- `./data/sessions.db`：单个 SQLite 文件承载 **会话、查询偏好、SQL 历史记忆、Admin HDC 映射** 四类数据。
- compose 通过 `./data:/app/data` 卷挂载持久化，**升级时勿删除此目录**。
- 备份：`cp ./data/sessions.db ./data/sessions.db.bak`

---

## 六、常见问题

### 1. 容器反复 Restarting，日志报 `ValueError: invalid literal for int()`

**原因**：`WEB_CONCURRENCY` 被设为空字符串，gunicorn 上游在 import 阶段 `int('')` 崩溃。
**解决**：不要 `export WEB_CONCURRENCY=`（空赋值）；要么不设（走自动 `2*CPU+1`），要么 `export WEB_CONCURRENCY=4`（具体数字）。

### 2. SQL Memory 语义检索无结果 / embedding 报错

**原因**：`LLM_EMBEDDING_PROVIDER=ollama` 但容器内无 ollama 服务。
**解决**：`export LLM_EMBEDDING_PROVIDER=openai`（用 LLM 网关 embedding）或 `auto`（OpenAI 优先回退 ollama）。

### 3. 容器启动失败，提示某变量必填

**原因**：compose 的 `${VAR:?...}` 约束生效，敏感配置未注入。
**解决**：确认 `LLM_API_KEY`/`ONEDBA_ACCESS_TOKEN`/`ONEDBA_ENV`/`ADMIN_API_TOKEN` 均已 export 到部署环境。

### 4. Admin API 返回 503

**原因**：`ADMIN_API_TOKEN` 为空。
**解决**：注入非空 token；或确认对应子能力的开关已开（SQL Memory 端点需 `SQL_MEMORY_ENABLED=true`）。

### 5. 端口冲突

**解决**：`export HOST_PORT=8080` 后 `docker compose up -d`。

---

## 七、生产环境检查清单

- [ ] `ONEDBA_ENV=prd`（生产环境）
- [ ] `ADMIN_API_TOKEN` 为强随机值，非空
- [ ] `LLM_EMBEDDING_PROVIDER` 为 `openai` 或 `auto`（非 ollama）
- [ ] `DEBUG=false`
- [ ] `LANGFUSE_ENABLED=true` 且 keys 已注入（便于线上排障）
- [ ] `./data` 目录已纳入定期备份
- [ ] 健康检查通过：`curl localhost:8000/health` 返回 200
- [ ] 宿主防火墙仅放行必要端口，`8000` 不直接暴露公网（经反代/网关）
