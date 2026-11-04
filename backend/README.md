# MiniMax Code2API 后端

FastAPI 模块化单体后端。要求 Python 3.11+。从仓库根目录查看[项目说明](../README.md)，完整接口契约见[后端 API 文档](../docs/api.md)，部署和密钥配置见[部署文档](../docs/deployment.md)。

## 本地启动

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# 将生成值写入 ENCRYPTION_KEY，并设置高熵 ADMIN_TOKEN。
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8045
```

Swagger 位于 `/docs`。管理端使用 `Authorization: Bearer $ADMIN_TOKEN`；网关使用创建的 API Key。使用 `x-minimax-region: cn|global` 选择隔离的账号区域。服务默认应保持仅本机可访问；外部部署必须使用 TLS 和访问控制。

## 当前实现与限制

- 账号 CRUD、账号分组隔离、API Key、请求日志、积分流水、概览、单账号签到和余额同步已提供基础后端实现。
- 网关目前只转发 Anthropic Messages（含 SSE），Chat Completions/Responses 返回 501；`/v1/models` 也返回 501。
- 新账号 `health=unknown`，当前没有认证/健康检查接口；只有已通过可信流程验证并标记为 healthy 的账号才会进入网关候选池。
- 后端不实现桌面端 auth-lease broker，要求操作员安全提供兼容 Bearer token；签到另需 `real_user_id`。
- 签到路径及签名遵循检查过的官方 CLI 源码，但上游端点不是稳定公开 API，可能变化。

签到奖励仅在上游领取响应提供可校验字段时记录，并等待独立余额同步。Token Plan remains 不是通用钱包余额保证；余额快照独立于推测的 API 消耗，不生成实际扣款结论。

## API 与测试

完整接口、请求格式及数据语义见[API 文档](../docs/api.md)。

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app tests migrations
```
