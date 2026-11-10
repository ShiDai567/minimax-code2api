# MiniMax Code2API

MiniMax Code 国内版与国际版账号的管理后台，以及 Anthropic / OpenAI 协议网关。

后端是 Django 5 + Django REST framework，前端是 Next.js 16。页面直接读取管理 API，不再使用 mock 数据。未核实的上游能力（余额、模型发现、token 刷新）会返回明确错误，不会被伪装成成功。

## 功能与状态

| 能力 | 当前状态 |
| --- | --- |
| 国内版 (`cn`) / 国际版 (`global`) 账号、分组 | 分开存储、分开查询，仪表盘可以汇总 |
| 账号凭证 | Fernet 加密存储，列表只返回脱敏值 |
| API Key | 只在创建成功时返回明文，数据库只存 SHA-256 摘要 |
| Anthropic Messages 网关 | 转发与 SSE 已实现，需要已验证且健康的账号 |
| OpenAI Chat / Responses | 只做纯文本转换，不支持的字段返回 400 |
| 模型发现 | 只有配置了已核实的 `MODEL_DISCOVERY_URLS` 才可用，否则返回 501 |
| 手动与批量签到 | 已实现；签到成功不等于积分到账 |
| 余额同步 | 只有配置了已核实的 `BALANCE_ADAPTERS` 才记账 |
| 自动签到 | `manage.py checkin_worker` 按数据库租约执行，失败不会被重复回放 |

## 仓库结构

- `frontend/`：Next.js 16 App Router 管理界面，数据经 `src/lib/api.ts` 读取。
- `backend/`：Django 项目。应用在 `apps/`，上游适配器在 `adapters/`，业务逻辑在 `services/`。
- `docker-compose.yml`：MySQL 8.0、后端、签到 worker、前端。
- `API_SPEC.md`、`DATABASE_SCHEMA.md`、`BACKEND_PLAN.md`、`INTEGRATION_PLAN.md`：接口与数据约定。

## 本地开发

### 后端

使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python 和依赖，要求 Python 3.11 或更高版本（默认使用 3.13）。`uv sync` 会自动创建 `.venv` 并安装锁定的依赖及开发工具，无需手动激活虚拟环境。

```bash
cd backend
uv sync --locked
```

生成密钥并导出运行所需的变量：

```bash
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
export ENCRYPTION_KEY=上一步的输出
export ADMIN_TOKEN=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')
export CONSOLE_PASSWORD=设置一个密码
```

不设置 `DATABASE_URL` 时使用 `backend/db.sqlite3`。

```bash
uv run python manage.py migrate
uv run uvicorn config.asgi:application --host 127.0.0.1 --port 8045
```

另开一个终端运行自动签到：

```bash
uv run python manage.py checkin_worker --interval 15
```

健康检查是 `http://127.0.0.1:8045/health`。页面登录只需要 `CONSOLE_PASSWORD`。脚本可以直接用 `Authorization: Bearer $ADMIN_TOKEN`。网关请求用管理界面创建的 API Key，与管理端凭证不通用。

测试：

```bash
cd backend
uv run pytest
```

依赖声明在 `backend/pyproject.toml`，解析结果锁定在 `backend/uv.lock`，两者需要一起提交。在 `backend/` 下使用 `uv add 包名` 添加运行依赖、`uv add --dev 包名` 添加开发依赖、`uv remove 包名` 删除依赖。更新依赖时运行 `uv lock --upgrade`，再执行 `uv sync --locked` 和测试。生产环境使用 `uv sync --locked --no-dev`；Docker 构建也使用相同的锁文件。

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发站点是 `http://localhost:3000`，默认请求 `http://127.0.0.1:8045`。用 `NEXT_PUBLIC_API_BASE_URL` 修改地址。这个变量会进入浏览器包，不能放任何密钥。

```bash
npm run lint
npx tsc --noEmit
npm run build
```

## Docker Compose

复制 `.env.example` 为 `.env`，填入 `ENCRYPTION_KEY` 后再启动：

```bash
docker compose up --build
```

前端在 `http://localhost:3000`，后端在 `http://localhost:8045`。

## 重要说明

MiniMax Code 的登录令牌和签到端点是上游实现细节，不是稳定的公开 API。本项目不实现桌面端的 auth-lease broker，操作者需要自己提供兼容的 Bearer token。不要把真实凭证提交到仓库、日志或工单中。
