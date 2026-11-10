# MiniMax Code2API 后端架构与开发计划

日期：2026-11-10。本文记录开工前已核实的事实，以及据此落地的架构。不编造上游地址、签到字段或积分规则。

## 1. 现状

- 前端在 `frontend/`，Next.js 16 App Router + React 19。全部页面集中在 `frontend/src/components/console.tsx`，经 `frontend/src/lib/api.ts` 读取管理 API，默认指向 `http://127.0.0.1:8045`。
- 仓库根目录的 README / docs 仍描述已删除的 Flask 后端。该实现不在工作区，但完整保留在 git `7864857`。它是目前唯一经过本仓库测试覆盖的上游协议实现，Django 版以它为协议来源，而不是重新猜测。
- 外部 GitHub（官方 CLI、syxscott/minimax-code2api、decolua/9router）在本环境 TLS 握手失败，无法在本次开发中重新拉取。差异以 git 历史中已落地、并有测试断言的行为为准。

## 2. 已核实的上游行为（来自 `7864857` 的 providers / gateway 及对应测试）

这些地址和字段是先前实现里被测试锁定的，不是本次臆造：

| 用途 | 国内版 | 国际版 |
| --- | --- | --- |
| LLM 网关 | `https://agent.minimax.cn` | `https://agent.minimax.io` |
| 签到 / 公共接口 | `https://agent.minimaxi.com` | `https://agent.minimax.io` |

注意国内版两个域名不同：`agent.minimax.cn` 与 `agent.minimaxi.com`。不能合并。

LLM 转发：

- `POST {gateway}/mavis/api/v1/llm/v1/messages`
- `POST {gateway}/mavis/api/v1/llm/v1/messages/count_tokens`
- 头：`Authorization: Bearer <token>`、`User-Agent: MiniMaxAgent`、`X-Mavis-Session-Id`、`X-Mavis-Agent-Id: main`、`X-Mavis-Timezone-Offset`、`anthropic-version`
- 协议是 Anthropic Messages。OpenAI Chat / Responses 由本网关转换，不是上游原生接口。

签到（官方 CLI 公开的状态 + 领取路径，尚未用真实账号实测）：

- `GET /minimax-cloud/api/v1/signin/status`
- `POST /minimax-cloud/api/v1/signin/claim`，body 固定 `{}`
- 需要同一区域的 Bearer token 和 `real_user_id`
- 查询参数含 `device_platform=web`、`biz_id=3`、`app_id=3001`、`version_code=22201`、`is_desktop=1`、`client=mcode`、`user_id`、语言（国内 `zh` / 国际 `en`）
- 签名头 `yy`、`x-signature`、`x-timestamp` 按 CLI 算法计算，算法留在国内/国际各自的 checkin 模块，不上升为公共协议
- 面板 `days[].status`：1 未到、2 可领、3 已领、4 失效；`claim_result` 1 成功、2 已领
- 响应里的 `points` 只是上游报告的奖励，**不代表积分已到账**

明确没有核实、因此不实现为“真接口”的能力：

- Token 刷新。没有已验证的 refresh 端点。适配器保留 `refresh_token()`，调用时返回“上游不支持”，不伪造刷新。
- 通用钱包 / 积分余额。没有已验证的余额 URL。余额只能走操作者配置的 HTTPS 适配器（`BALANCE_ADAPTERS`），未配置时返回 501，不编造余额。
- 模型目录。没有已验证的默认模型列表。`GET /v1/models` 只在配置了 `MODEL_DISCOVERY_URLS` 时转发；否则 501。管理端“模型”表只收录网关实际转发成功后上游回显的 model id，或发现接口返回的 id。不硬编码 `MiniMax-M3` 等名称。
- 积分消耗公式。上游 Messages 响应只稳定给出 token usage，不给出积分。没有核实的换算规则，因此不按 token 估算积分。

## 3. 架构

```
backend/
  config/            Django 5 项目，ASGI，分环境 settings
  apps/              领域模型与管理 API（薄 view）
  adapters/          国内 / 国际各自的 HTTP 实现，互不复用请求细节
  services/          账号、签到、积分、网关、账号池、模型路由
  common/            异常、分页、加密、权限
  tests/
```

- Web：Django 5 + DRF + drf-spectacular。ASGI（uvicorn）承载 SSE，不把流式响应缓冲后再返回。
- 持久化：MySQL 8.0。测试用 SQLite，业务约束在应用层与数据库约束双写。
- 不引入 Redis。定时签到用数据库租约 + 独立 `manage.py checkin_worker`，重启后按 `schedule_key` 恢复，不补偿停机期间错过的日期。
- 管理端与网关是两套认证：管理端接受 `ADMIN_TOKEN`，或用 `CONSOLE_PASSWORD` 登录后签发的签名令牌（密码来自环境变量，不入库，不建会话表）；网关只认 API Key 的 SHA-256。
- 凭证 Fernet 加密。列表、日志、错误响应都不回传明文 token。

## 4. 业务闭环（本次必须落地）

1. 账号：分区 CRUD、分组、导入、加密、可选的 count_tokens 验证。验证失败不得标为 healthy。
2. 签到：单账号、批量、按区域、定时。同一账号同一 UTC 日不重复领取；pending 不自动重放（上游可能已经领取）。
3. 积分：流水与余额同一事务、行锁、`balance_after = balance_before + delta`。上游同步只追加 `credit_sync` 差额，不覆盖历史流水。没有核实来源的变动不写入已确认账本。
4. 网关：API Key、账号池（轮询 / 积分优先 / 最近活跃 / 最少使用）、Anthropic 透传 + SSE、OpenAI Chat / Responses 的纯文本非流式转换。流式在结束后写日志。
5. 管理端全部页面改读这些接口，按钮触发真实写操作。

## 5. 明确不做的事

- 不重写前端视觉，不改导航和信息架构。
- 不用 Flask / FastAPI，不引入 Redis。
- 不用固定假数据冒充余额、模型或积分消耗。
- 不实现桌面端本地 auth-lease broker。操作者自行提供已授权的 Bearer token。
