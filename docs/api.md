# 后端 API 与数据语义

默认后端地址为 `http://127.0.0.1:8045`。除 `/health` 和网关端点外，管理 API 使用：

```http
Authorization: Bearer <ADMIN_TOKEN>
```

网关端点使用已创建的 `sk-m2a-...` API Key。国内版标识为 `cn`，国际版为 `global`；账号和分组不可跨区域关联。网关区域通过 `x-minimax-region: cn|global` 选择，省略时默认为 `cn`。

## 管理 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 无管理认证的进程健康状态和粗粒度能力标记 |
| `GET` | `/api/v1/capabilities` | 能力标记；目前签到/积分/控制项不代表已全量实现 |
| `GET` | `/api/v1/accounts?region=cn` | 列出账号，可按区域筛选 |
| `POST` | `/api/v1/accounts` | 创建账号 |
| `PATCH` | `/api/v1/accounts/{id}` | 修改账号资料、凭证、分组、启用状态 |
| `DELETE` | `/api/v1/accounts/{id}` | 删除账号；被账本或签到记录引用时数据库会拒绝删除 |
| `POST` | `/api/v1/accounts/bulk-delete` | 批量删除，JSON body 为整数 ID 数组 |
| `GET` | `/api/v1/groups?region=cn` | 列出分组 |
| `POST` | `/api/v1/groups` | 创建区域分组 |
| `GET` | `/api/v1/keys` | 列出 API Key 元信息，不返回明文密钥 |
| `POST` | `/api/v1/keys` | 创建 API Key，明文只在此响应中返回一次 |
| `PATCH` | `/api/v1/keys/{id}?enabled=false` | 启用/停用 API Key |
| `DELETE` | `/api/v1/keys/{id}` | 删除 API Key |
| `GET` | `/api/v1/logs?limit=50&offset=0` | 分页读取最近请求日志，limit 上限 500 |
| `GET` | `/api/v1/credits` | 读取最近 500 条积分/余额流水 |
| `GET` | `/api/v1/dashboard` | 当前持久化数据的概览；部分无来源指标为 `null` |
| `POST` | `/api/v1/checkin/run?account_id={id}` | 对单个账号执行一次签到尝试 |
| `POST` | `/api/v1/accounts/{id}/balance-sync` | 请求上游 Token Plan remains 并记录识别到的余额快照 |

创建账号示例：

```json
{
  "region": "global",
  "name": "Global account",
  "identifier": "operator@example.test",
  "credential": "<compatible-bearer-token>",
  "real_user_id": "<upstream-user-id>",
  "group_id": null,
  "note": ""
}
```

`real_user_id` 仅用于上游 MCode 签到签名请求，可为空；未提供时签到端点返回 422。创建账号响应只返回脱敏凭证。账号新建后的 `health` 为 `unknown`，不会自动视为可用或自动进入网关路由池。

## 网关 API

| 方法 | 路径 | 当前行为 |
| --- | --- | --- |
| `POST` | `/v1/messages` | 转发 Anthropic Messages；支持不缓冲 SSE 流式转发 |
| `POST` | `/v1/chat/completions` | 返回 501，OpenAI Chat 转换器未实现 |
| `POST` | `/v1/responses` | 返回 501，OpenAI Responses 转换器未实现 |
| `GET` | `/v1/models` | 返回 501；当前无已验证的上游模型发现适配器 |

请求需使用 `Authorization: Bearer <API_KEY>`。Messages 请求按 `x-minimax-region` 选取对应区域内 `enabled=true` 且 `health=healthy` 的账号。找不到可用账号时返回上游错误；后端当前没有公开的账号健康验证端点，因此账号需要由操作员通过可信流程确认，并通过管理 API 更新状态。

转发时仅向上游传递必要的 Anthropic 请求头，并使用区域对应的 Mavis LLM 路径。日志记录请求状态、延迟、协议、账号/API Key 引用和已过滤头部；不会将完整请求体写入日志。

## 签到与积分

签到端点首先依据上游返回的当天状态决定是否领取。已领取状态不会重复领取；不可领取状态不会报告成功。领取成功时，只有上游响应包含 `claim_id` 和数值 `points` 才接受结果。

签到响应中的 reward 是上游报告值，账本 certainty 标为 `reported`，arrival 为 `pending`；它不证明余额已到账。余额同步使用 Token Plan remains 上游接口，只接受代码识别的余额字段，并写入 `balance_reconciliation` 快照。快照的流水 delta 为 0，不能解释为 API 使用扣款。

网关日志中的 token usage、估算消耗和实际上游扣款目前不能完整关联；不要把请求数或估算值当作真实积分扣除。

## 错误与状态

- `401`：管理 Token 或网关 Key 缺失/无效。
- `409`：重复签到尝试或账号唯一性冲突等状态冲突。
- `422`：字段无效、跨区域分组、签到缺少 `real_user_id` 等。
- `501`：协议适配或模型发现尚未实现。
- `502`：上游签到/余额请求失败，或网关上游不可用。
- `503`：配置缺失或没有满足条件的可用账号。

列表响应的 `source: "live"` 表示数据来自本后端数据库，不意味着该字段已由 MiniMax 上游实时确认。具体可信度以字段、`certainty`、同步时间及本文件的语义为准。
