# Xueqiu Investor Intelligence System

面向投资者行为变化的、数据源无关的研究情报系统。本仓库当前处于 Phase 0：Project Bootstrap。

## Local setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn backend.app.main:app --reload
```

默认未配置 `.env` 时使用本地 SQLite；`.env.example` 提供 PostgreSQL 开发配置。

## Verification

```powershell
pytest
ruff check .
```

API 启动后可访问 `GET /health` 检查应用与数据库连通性。


## Xueqiu post collector smoke test

首次使用时启动可见浏览器，并在浏览器中手动完成登录：

```powershell
python -m collectors.xueqiu.smoke --authenticate
```

确认数据库中已存在对应 Investor 后，采集最多 5 条原创公开帖子：

```powershell
python -m collectors.xueqiu.smoke `
  --investor-id <INVESTOR_UUID> `
  --platform-user-id <XUEQIU_USER_ID> `
  --homepage-url https://xueqiu.com/u/<XUEQIU_USER_ID> `
  --limit 5
```

Collector 默认通过 Playwright `channel="msedge"` 启动系统 Edge，无需配置固定路径。
如显式设置 `XUEQIU_BROWSER_EXECUTABLE_PATH`，该路径会覆盖
`XUEQIU_BROWSER_CHANNEL`。
认证状态默认保存在已被 Git 忽略的 `.local/xueqiu/storage_state.json`。

如果雪球显示登录、滑动验证或访问限制页面，Collector 会停止并返回明确错误，
不会尝试绕过。

## Core intelligence pipeline demo

无需实时雪球采集，使用 Manual Import 与 Mock Extractor 运行完整核心链路：

```powershell
python -m pipeline.demo
```
