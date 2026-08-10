# DBAgent 交付检查清单

本文档用于上线前验收和运维交接。详细 API 说明见 `docs/api-guide.md` 和 `docs/admin-api-guide.md`。

## 1. 配置检查

- [ ] `.env.example` 是配置基准，生产 `.env` 不提交到 git
- [ ] `LLM_API_KEY`、`ONEDBA_ACCESS_TOKEN`、`ADMIN_API_TOKEN` 已通过 Secret 或受控环境变量注入
- [ ] `ONEDBA_ENV=prd`
- [ ] `DEBUG=false`
- [ ] `STORAGE_BACKEND=sqlite`
- [ ] 如启用 SQL Memory，embedding provider 为 `openai` 或 `auto`
- [ ] 如启用 HDC 或 KB，OpenViking 地址可达

## 2. 部署验收

```bash
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/health
```

通过标准：

- [ ] 容器状态为 `Up` 或 `healthy`
- [ ] `/health` 返回 200
- [ ] 启动日志显示 LLM、OneDBA、Storage、HDC、SQL Memory、Admin API 状态
- [ ] `data/sessions.db` 已创建并持久化挂载

## 3. 回归验收

默认本地验收：

```bash
bash scripts/acceptance.sh
```

带本地服务启动：

```bash
bash scripts/acceptance.sh --start-server
```

包含外部依赖和评测：

```bash
bash scripts/acceptance.sh --with-external --with-evaluation
```

通过标准：

- [ ] 默认验收 `FAIL=0`
- [ ] 外部依赖失败项已有明确原因和豁免说明
- [ ] 评测报告已归档

## 4. 回滚和备份

备份：

```bash
cp data/sessions.db "data/sessions.db.bak.$(date +%Y%m%d%H%M%S)"
```

回滚：

```bash
git checkout <known-good-commit>
docker compose build
docker compose up -d
curl http://localhost:8000/health
```

## 5. 安全检查

- [ ] 服务端口不直接暴露公网
- [ ] Admin API 仅允许可信调用方访问
- [ ] HDC 删除、用户注销等破坏性接口有额外访问控制
- [ ] 日志不输出密钥、完整 Authorization header 或敏感查询结果
