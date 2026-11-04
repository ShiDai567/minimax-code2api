# 部署与配置

## 环境要求

- Python 3.11+
- Node.js 与 npm，版本以 `frontend/package.json` 和 lockfile 为准
- SQLite（默认）或受支持的 SQLAlchemy MySQL 驱动/连接串配置

## 后端配置

从 `backend/` 执行命令。先安装依赖并复制配置：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

配置项：

| 变量 | 用途 | 默认/要求 |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy 数据库连接 | `sqlite:///./data/code2api.db` |
| `ADMIN_TOKEN` | 所有管理 API 的 Bearer Token | 必须设置为高熵随机值 |
| `ENCRYPTION_KEY` | Fernet 账号凭证加密密钥 | 必须设置；使用 Fernet URL-safe base64 key |
| `HOST` | 文档配置项 | `127.0.0.1`；启动命令需显式引用 |
| `PORT` | 文档配置项 | `8045`；启动命令需显式引用 |
| `UPSTREAM_TIMEOUT_SECONDS` | 网关上游请求超时 | `300` |
| `DEFAULT_MODEL` | 预留默认模型配置 | 当前未用于模型发现/映射 |

生成加密密钥：

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

`ENCRYPTION_KEY` 丢失或轮换后，旧账号凭证无法解密。请通过受控密钥管理系统备份，并制定显式的重新加密迁移流程；不要在已有数据上直接换 key。

数据库迁移和启动：

```bash
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8045
```

SQLite 文件的父目录会在连接时创建。生产环境使用 MySQL 时，应先安装对应数据库驱动，并针对实际数据库运行迁移和备份恢复测试；仓库没有提供生产容器编排或数据库运维配置。

## 前端配置

```bash
cd frontend
npm ci
npm run dev
```

前端 API client 的服务地址可通过构建期 `NEXT_PUBLIC_API_BASE_URL` 指定，默认 `http://127.0.0.1:8045`。浏览器跨域访问后端时需要由部署层配置 CORS 或同源反向代理；当前 FastAPI 应用没有配置 CORS 中间件。

管理 Token 不可放入 `NEXT_PUBLIC_*` 变量。前端目前仍以 mock 数据渲染为主，配置 API base URL 本身不会自动切换所有页面到真实后端。

## 运行和升级

- `/health` 可用于进程级探测，不代表上游凭证可用或模型网关已具备健康账号。
- 每次升级前备份数据库和加密密钥；部署新代码前执行 `alembic upgrade head`。
- 默认监听 localhost。外部访问应置于认证反向代理/TLS 后，并限制管理 API 网络访问。
- 上游 MiniMax Code 接口可能变化；上线前应针对每个区域使用授权账号做签到、余额和 Anthropic 请求验证。

## 本地检查

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
