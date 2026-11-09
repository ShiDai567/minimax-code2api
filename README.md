# MiniMax Code2API

> **开发状态更新：** 后端具备账号、分组、密钥、签到任务和有限协议网关；上游尚未使用真实凭证验证，前端仍为模拟页面。具体能力与限制请以 [后端开发状态](backend/README.md) 为准。

MiniMax Code 国内版与国际版账号管理及协议网关。仓库包含 Next.js 管理界面和 Flask 后端；当前项目仍在开发中，前端页面主要使用本地 mock 数据，尚未完成与后端的逐页联调。

## 功能与状态

| 能力 | 当前状态 |
| --- | --- |
| 国内版 (`cn`) / 国际版 (`global`) 账号、分组隔离 | 后端已实现基础 CRUD；两区域独立存储 |
| 账号凭证 | Fernet 加密后存储；列表只返回脱敏值 |
| API Key | 仅创建成功时返回明文；数据库仅存 SHA-256 摘要 |
| Anthropic Messages 网关 | 后端转发及 SSE 流式响应已实现；需要已验证且健康的账号 |
| OpenAI Chat Completions / Responses | 仅纯文本非流式转换；其他输入明确拒绝 |
| 模型发现 (`GET /v1/models`) | 需管理员配置已验证的区域模型列表 URL；默认返回 HTTP 501 |
| 手动签到 | 根据官方 CLI 协议实现；需要兼容 Bearer token 和 `real_user_id`，尚未实测 |
| Token Plan 余额同步 | 需配置已验证的区域适配器；快照不代表 API 消耗或通用钱包余额 |
| 自动/批量签到、定时任务 | 数据库任务队列与独立 worker 已实现；需要另外运行 worker |
| 前端到后端联调 | API client 已创建，页面仍主要读取 mock 数据 |

签到成功不代表积分已到账。签到返回的奖励只按上游响应记录为 `reported`；配置的计划快照不构成积分到账对账，网关请求消耗不会伪装成上游实际扣款。

## 仓库结构

- `frontend/`：Next.js 16 App Router、React 19、TypeScript、Tailwind CSS v4 管理界面。
- `backend/`：Flask 模块化 API、SQLAlchemy、SQLite/MySQL 兼容的数据层、Alembic 迁移及上游 provider。
- `docs/`：API、部署和安全说明。
- `AGENTS.md`：仓库开发约束及领域规则。

## 本地开发

### 后端

要求 Python 3.12 或更高版本。

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

生成 Fernet 密钥：

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

将生成值写入 `backend/.env` 的 `ENCRYPTION_KEY`，同时设置高熵 `ADMIN_TOKEN`。然后初始化数据库并启动：

```bash
flask --app wsgi db upgrade
flask --app wsgi run --host 127.0.0.1 --port 8045
```

健康检查为 `http://127.0.0.1:8045/health`。管理端请求使用 `Authorization: Bearer $ADMIN_TOKEN`；网关请求使用管理界面创建的 API Key。

自动签到和批量任务需要另开一个终端运行 `flask --app wsgi worker`，配置细节和限制见 [部署说明](docs/deployment.md)。

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发站点默认地址为 `http://localhost:3000`。`NEXT_PUBLIC_API_BASE_URL` 可用于配置 API client 指向的后端地址，但当前页面尚未全面使用该 client。不要将管理端 `ADMIN_TOKEN` 放入 `NEXT_PUBLIC_*` 环境变量或浏览器代码。

## 验证

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app tests migrations
```

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

## 文档

- [后端 API 与数据语义](docs/api.md)
- [部署与配置](docs/deployment.md)
- [安全说明与能力边界](docs/security-and-limitations.md)
- [后端开发说明](backend/README.md)
- [前端开发说明](frontend/README.md)

## 重要说明

MiniMax Code 登录令牌和签到端点属于上游实现细节，不是稳定的通用公开 API。此项目不实现桌面端本地 auth-lease broker；操作者需要自行安全地提供兼容的 Bearer token。不要把真实凭证提交到仓库、日志或工单中。外网部署前必须配置 TLS、访问控制和密钥管理，并评估上游条款及凭证授权范围。
