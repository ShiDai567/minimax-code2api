# 部署与配置

后端要求 Python 3.11 或更高版本。上游行为尚未用真实账号验证，不要直接暴露到公网。

本地启动步骤见仓库根目录 [README](../README.md)。用 Docker 时复制根目录的 `.env.example` 为 `.env`，填入 `ENCRYPTION_KEY` 后执行 `docker compose up --build`。

Django 启动时读取 `backend/.env`。`ENCRYPTION_KEY` 丢失或更换后，已保存的账号凭证无法解密，请单独备份。

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

| 环境变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | 默认 `sqlite:///db.sqlite3`。MySQL 示例：`mysql://code2api:code2api@127.0.0.1:3306/code2api` |
| `DJANGO_SECRET_KEY` | Django 密钥 |
| `ADMIN_TOKEN` | 管理端 Bearer 令牌 |
| `ENCRYPTION_KEY` | Fernet 密钥，加密账号凭证 |
| `CONSOLE_PASSWORD` | 控制台登录密码，只从环境变量读取，不入库。未设置时登录接口返回 503 |
| `CORS_ALLOWED_ORIGINS` | 允许的前端来源，默认 `http://localhost:3000,http://127.0.0.1:3000` |
| `MCODE_APP_VERSION` | 签到请求里的客户端版本标记，默认 `0.1.0` |
| `BALANCE_ADAPTERS` | 可选 JSON。按区域给出已核实的 HTTPS 地址、数值字段和单位 |
| `MODEL_DISCOVERY_URLS` | 可选 JSON。按区域给出已核实的 HTTPS 模型列表地址 |

```sh
BALANCE_ADAPTERS='{"cn":{"url":"https://trusted.example/plan","field":"data.remaining","unit":"credits"}}'
MODEL_DISCOVERY_URLS='{"cn":"https://trusted.example/v1/models"}'
```

只填写可信的 HTTPS 地址。这两个配置会收到对应区域的账号凭证。返回的数值只是上游报告的快照，不会被当成钱包余额。

自动签到需要单独运行 `python manage.py checkin_worker --interval 15`。Compose 里的 `checkin-worker` 服务做同样的事。

验证：

```sh
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -q
```
