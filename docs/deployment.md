# 部署与配置

后端要求 Python 3.12+。前端独立运行，仍使用 mock 数据。上游尚未真实验证，此服务不应直接暴露公网或用作生产系统。

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

在 `.env` 中设置随机的 `ADMIN_TOKEN`（至少 32 字符）及生成的 `ENCRYPTION_KEY`。Flask CLI 通过 python-dotenv 加载 `.env`；Gunicorn 等启动方式应由进程管理器显式提供环境变量。妥善备份加密密钥，丢失或直接替换会导致已有凭证无法解密。

```sh
flask --app wsgi db upgrade
flask --app wsgi run --host 127.0.0.1 --port 8045
```

批量/定时签到需要在另一个进程启动 `flask --app wsgi worker`。支持 `--once` 处理最多一个任务，`--interval 10` 设置空闲轮询秒数。进程停止时不执行任务；启动后会恢复到期租约。任务按数据库防重，计划使用设置中的 IANA 时区；worker 应由进程管理器监控。上游请求默认超时 30 秒，任务租约 5 分钟。SQLite 适合单机；其他数据库需自行安装驱动并验证迁移、并发和备份恢复。

| 环境变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL，默认 `sqlite:///code2api.db`，相对 Flask instance 目录 |
| `ADMIN_TOKEN` | 高熵管理口令，至少 32 字符 |
| `ENCRYPTION_KEY` | Fernet 密钥 |
| `MCODE_APP_VERSION` | 签到请求客户端版本标记，默认 `0.1.0`；上游可能要求其他版本 |
| `BALANCE_ADAPTERS` | 可选 JSON；按区域定义已验证 HTTPS URL、数值字段路径和单位 |
| `MODEL_DISCOVERY_URLS` | 可选 JSON；按区域定义兼容 OpenAI `data` 数组的已验证 HTTPS 模型 URL |

可选适配器配置示例（必须替换为经过验证的可信 URL，服务会向其发送相应区域账号凭证）：

```sh
BALANCE_ADAPTERS='{"cn":{"url":"https://trusted.example/plan","field":"data.remaining","unit":"tokens"}}'
MODEL_DISCOVERY_URLS='{"cn":"https://trusted.example/v1/models"}'
```

不要使用不受信任的目标或明文 HTTP。适配器目标由部署者控制，禁用 HTTP 重定向和代理环境变量；返回数值仍只是上游报告的计划快照，不自动成为钱包余额。API 不提供桌面端本地 auth-lease broker，需由操作者提供获得授权的兼容 token。

上线前应在隔离环境中针对每个区域验证真实签到、模型和网关行为；通过 TLS、访问控制、密钥管理、备份、限流和审计保护管理 API。当前无 CORS，建议同源反向代理。不要将管理 Token 放入浏览器或 `NEXT_PUBLIC_*` 变量。当前前端 API client 与后端尚未完成完整集成。

验证：`python -m pytest -q` 和 `python -m compileall -q app tests migrations`。
