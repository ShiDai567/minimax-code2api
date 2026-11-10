# API 规范

两套认证，互不通用。

- 管理端：`Authorization: Bearer <ADMIN_TOKEN>`，或登录后拿到的签名令牌。`/health` 与 `/api/schema/` 除外。
- 网关：`Authorization: Bearer <API Key>` 或 `x-api-key`。管理 token 不能调用网关，API Key 不能调用管理端。

管理端成功响应：

```json
{"success": true, "source": "live", "fetchedAt": 0, "data": {}}
```

列表 `data` 为 `{ "items": [], "total": 0 }`。错误：HTTP 状态 + `{"detail": "...", "error": {"code": "..."}}`。`source=live` 只表示来自本库，不表示已与上游核对。余额未知时字段为 `null`，不用 0 冒充。

时间戳对前端用毫秒 epoch，与 `frontend/src/lib/types.ts` 一致。

## 管理端

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 无需认证 |
| GET | `/api/v1/health/` | 同上，带尾斜杠别名 |
| GET | `/api/v1/capabilities/` | 能力开关，前端据此隐藏不支持的控件 |
| POST | `/api/v1/auth/login/` | `{password}`，与 `CONSOLE_PASSWORD` 比对。通过后签发 7 天签名令牌，不入库。未配置密码返回 503。改密码后旧令牌立即失效 |
| GET | `/api/v1/dashboard/` | 跨区域汇总。无来源的余额、消耗为 `null` |
| GET | `/api/v1/dashboard/?range=24h\|7d\|30d` | 趋势 |
| GET POST | `/api/v1/accounts/?region=cn\|global` | 列表必须带 region |
| GET PATCH DELETE | `/api/v1/accounts/{id}/` | |
| POST | `/api/v1/accounts/import/` | 批量导入 |
| POST | `/api/v1/accounts/bulk-delete/` | `{region, account_ids}` |
| POST | `/api/v1/accounts/{id}/verify/` | `{model}`，count_tokens 验证 |
| POST | `/api/v1/accounts/{id}/checkin/` | 单账号签到 |
| POST | `/api/v1/accounts/{id}/sync-credits/` | 上游快照；未配置适配器 501 |
| POST | `/api/v1/accounts/{id}/enable/` `/disable/` | |
| GET POST | `/api/v1/groups/?region=` | |
| PATCH DELETE | `/api/v1/groups/{id}/` | |
| GET POST | `/api/v1/keys/` | 创建只此一次返回 `secret` |
| PATCH DELETE | `/api/v1/keys/{id}/` | 有日志时删除 409，改为停用 |
| GET | `/api/v1/models/?region=` | 仅已发现 / 已观察到的模型 |
| PATCH | `/api/v1/models/{id}/` | 启用开关 |
| POST | `/api/v1/models/discover/` | `{region}`，未配置发现 URL 则 501 |
| GET POST | `/api/v1/checkin/jobs/?region=` | 批量任务 |
| GET | `/api/v1/checkin/jobs/{id}/` | 进度 |
| GET | `/api/v1/checkin/records/?region=` | |
| GET | `/api/v1/credits/?region=` | 已确认流水 |
| GET | `/api/v1/credits/summary/?region=` | |
| GET | `/api/v1/credits/export/?region=` | CSV |
| GET | `/api/v1/logs/?region=` | |
| GET | `/api/v1/logs/{id}/` | |
| GET | `/api/v1/gateway/status/` | |
| POST | `/api/v1/gateway/start/` `/stop/` `/restart/` | 进程内开关，不杀进程 |
| GET | `/api/v1/gateway/runtime-logs/` | 内存环形缓冲，重启即失 |
| GET PATCH | `/api/v1/settings/` | |
| GET | `/api/v1/runtime/` | 组件健康 |

列表查询：`search`、`limit`、`offset`、`sort`、`order`、`enabled`、`health`、`status`、`protocol`。

账号创建：

```json
{"region":"cn","name":"","identifier":"","credential":"<bearer>","real_user_id":"","group_id":null,"note":"","model":""}
```

`model` 可选。给出则立即用 count_tokens 验证；失败时账号仍保存，但 `health` 不为 `healthy`。

## 网关

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| POST | `/v1/messages` | Anthropic 原样转发，SSE 透传 |
| POST | `/v1/messages/count_tokens` | 透传 |
| POST | `/v1/chat/completions` | 纯文本非流式转换；`stream`、tools、多模态返回 400/501，不静默丢弃 |
| POST | `/v1/responses` | 同上 |
| GET | `/v1/models` | 已配置发现 URL 才转发，否则 501 |

`x-minimax-region: cn|global` 选择区域，默认 `cn`。只使用该区域 `enabled` 且 `health=healthy` 的账号。无账号 503。上游 401/403 把该账号标为 `expired` 并尝试池中下一个，最多一次。上游错误正文不回传。

## 前端映射

| 页面 | 接口 |
| --- | --- |
| 仪表盘 | `GET /api/v1/dashboard/` |
| 国内 / 国际账号 | `GET/POST/PATCH/DELETE /api/v1/accounts/` |
| 分组 | `/api/v1/groups/` |
| 签到 | `/api/v1/checkin/records/`、`/api/v1/checkin/jobs/`、`/accounts/{id}/checkin/` |
| 积分 | `/api/v1/credits/` |
| API 服务 | `/api/v1/gateway/status/` |
| API Keys | `/api/v1/keys/` |
| 模型 | `/api/v1/models/` |
| 请求日志 | `/api/v1/logs/` |
| 设置 / 运行状态 | `/api/v1/settings/`、`/api/v1/runtime/` |
