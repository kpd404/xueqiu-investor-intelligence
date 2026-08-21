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

