# 后端 API 与数据语义

管理接口使用 `Authorization: Bearer <ADMIN_TOKEN>`；网关使用管理接口创建的 API Key（Bearer 或 Anthropic `x-api-key`）。`/health` 不需要认证。管理响应包含 `success`、`data`、`source: "live"`，字典字段也出现在顶层；错误含 `detail` 和 `error.code`。`live` 仅表示来自本地数据库，不表示已与上游核对。

除仪表盘汇总外，账号、分组、签到、积分和请求日志列表必须用 `region=cn` 或 `region=global` 筛选。列表支持 `limit`（1–500）、`offset`、`sort` 和 `order=asc|desc`；账号/分组/密钥/日志支持 `search`，账号支持 `enabled`、`health`、`group_id`，签到和日志支持 `status`，日志支持 `protocol`。排序字段以接口报错提示和实现为准。

## 管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/capabilities` | 服务能力，部分能力默认关闭 |
| GET, POST | `/api/v1/accounts` | 按区域查询、创建账号 |
| GET, PATCH, DELETE | `/api/v1/accounts/{id}` | 账号详情、修改、删除 |
| POST | `/api/v1/accounts/bulk-delete` | JSON `{ "region": "cn", "account_ids": [1] }`，原子删除 |
| GET, POST | `/api/v1/groups` | 区域分组列表和创建 |
| PATCH, DELETE | `/api/v1/groups/{id}` | 更新、删除分组 |
| GET, POST | `/api/v1/keys` | 密钥列表、创建；`/api-keys` 为兼容别名 |
| PATCH, DELETE | `/api/v1/keys/{id}` | 更新、停用、删除 |
| POST | `/api/v1/accounts/{id}/verify-model` | JSON `{ "model": "..." }`，调用上游 count_tokens 验证 |
| POST | `/api/v1/accounts/{id}/balance-sync` | 使用已配置适配器采集上游计划快照，默认 501 |
| POST | `/api/v1/checkin/run?account_id={id}` | 单账号手动签到 |
| GET | `/api/v1/checkins?region=cn` | 签到记录 |
| GET, POST | `/api/v1/checkin/jobs` | 批量签到任务列表及创建 |
| GET | `/api/v1/checkin/jobs/{id}` | 任务进度及逐账号结果 |
| GET | `/api/v1/credits?region=cn` | 已确认的账本流水；当前无上游到账/扣费适配器 |
| GET | `/api/v1/logs?region=cn` | 脱敏请求日志 |
| GET | `/api/v1/logs/{id}` | 日志详情 |
| GET | `/api/v1/dashboard` | 本地跨区域汇总；无来源余额/消耗为 `null` |
| GET, PATCH | `/api/v1/settings` | 定时签到设置 |
| GET | `/api/v1/runtime` | 进程、数据库、任务和能力状态 |

创建账号示例：

```json
{"region":"cn","name":"Account","identifier":"operator@example.test","credential":"<token>","real_user_id":"<user-id>","group_id":null,"note":""}
```

账号新建及替换凭证后为 `unknown`，调用验证接口后才可能变为 `healthy`。验证需要调用方提供上游支持的模型；模型不会硬编码。停用账号不会执行签到或承载网关请求。账号或密钥有历史引用时删除返回 409，保留审计历史。

批量任务创建示例：`{"region":"cn","account_ids":[1,2]}`。需运行独立 worker；任务状态和每项成功、失败、跳过数量保存在数据库中。设置示例：

```json
{"checkin":{"auto":true,"time":"09:00","timezone":"Asia/Shanghai","regions":["cn","global"]}}
```

worker 会在指定时区每天指定时间之后创建每区域一个任务，停机期间不会补偿历史日期。任务租约到期后可恢复，但进程崩溃时处于 `pending` 的签到不会自动再次领取，因为上游可能已执行。操作员需核对上游状态；目前没有自动解决未知状态的管理接口。签到按 UTC 日历日防重，跨时区日界附近应避免重复手动操作。

## 网关

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| POST | `/v1/messages` | Anthropic 原样转发；支持 SSE 流式透传 |
| POST | `/v1/messages/count_tokens` | Anthropic token 计数透传 |
| POST | `/v1/chat/completions` | 纯文本非流式 OpenAI Chat 转换 |
| POST | `/v1/responses` | 纯文本非流式 OpenAI Responses 转换 |
| GET | `/v1/models` | 调用已配置区域模型列表 URL；未配置返回 501 |

`x-minimax-region: cn|global` 指定上游区域，默认为 `cn`。只选择该区域已启用、已验证的账号。OpenAI 工具、多模态、流式及未列入支持范围的字段会报错，不会被静默忽略；上游非文本块也会报错。`max_tokens` 未提供时转换为 4096。模型名原样传递，不映射、不保证上游确实使用请求的模型。流式请求日志在响应结束后写入；流内容和 token 数不解析。

## 签到与数据可信度

签到实现采用官方 CLI 公开的状态和领取路径及签名，需要同一区域兼容 token 和 `real_user_id`，但本项目尚未用真实账号验证。上游可能随时变更。返回奖励标记 `reported`、`arrival: pending`；不写入已确认积分账本。上游计划快照单独存储，不推断钱包余额、API 消费或奖励到账。只有可确认前后余额及实际变动的流水才能满足账本约束 `balance_after = balance_before + delta`。

日志不存请求体；仅记录允许的 Anthropic 标头及认证头的存在情况，值均标记为 `[REDACTED]`。上游错误正文不透传，以免泄露敏感上下文。API Key 明文仅在创建响应出现，数据库只存 SHA-256 摘要。所有管理响应禁止缓存。
