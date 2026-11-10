# 数据库结构

MySQL 8.0，Django migrations。金额与积分一律 `DECIMAL(24, 6)`，禁止浮点。时间一律 UTC aware datetime。

## 表

### accounts_account

统一账号模型，`region` 区分国内 / 国际，不拆表。

| 列 | 说明 |
| --- | --- |
| id | PK |
| region | `cn` / `global` |
| name, identifier | 展示名、登录标识 |
| credential_encrypted | Fernet 密文，不回传 |
| real_user_id | 签到必需，可空 |
| session_id | 发给上游的 `X-Mavis-Session-Id`，换凭证时轮换 |
| group_id | 可空，FK 到同区域分组 |
| enabled | 停用后不参与签到和网关 |
| health | `unknown` / `healthy` / `error` / `expired` |
| health_reason, verified_at, last_active_at | |
| note | |
| current_credits | 本地已确认余额缓存，可空表示从未确认 |
| credits_synced_at | 上次把上游快照对进账本的时间 |
| last_checkin_at | |
| last_error | |
| created_at, updated_at | |

约束：`UNIQUE(region, identifier)`。`group` 必须同区域（应用层校验 + 分组表 `UNIQUE(id, region)` 供复合外键）。

### accounts_accountgroup / 成员

分组：`id, region, name, description, strategy, created_at`。`UNIQUE(region, name)`、`UNIQUE(id, region)`。

成员关系直接用 `accounts_account.group_id`，不另建成员表：一个账号只属于一个分组，与前端 `groupId` 一致。跨区域赋值在服务层拒绝。

### checkin_checkinrecord

一次签到尝试。`UNIQUE(account_id, day)`，`day` 为 UTC 日期，防止同日重复领取。

`status`: `pending` / `success` / `failed` / `skipped`。`reward` 为上游报告值，可空。`arrival`: `pending` / `credited` / `unknown`。`claim_id` 上游领取单号。`ledger_id` 可空，只有到账被余额差确认后才填写。

### checkin_checkinjob / checkin_checkintask

批量与定时任务。`schedule_key` 唯一，形如 `{timezone}:{local-date}:{region}`，保证同一本地日不重复排队。`lease_token` + `lease_until` 供 worker 抢占，崩溃后租约到期可恢复。任务项 `UNIQUE(job_id, account_id)`。

### credits_creditentry

已确认流水。只在变动前后余额都已知时写入。

`kind`: `checkin` / `api_usage` / `adjustment` / `credit_sync`。`delta`、`balance_before`、`balance_after`。数据库检查约束 `balance_after = balance_before + delta`。`upstream_id` 唯一，防止重复记账（签到用 `checkin:{claim_id}`，同步用 `sync:{account}:{synced_at_ms}`，请求用 `request:{request_id}`）。`request_id`、`checkin_id` 可空。

### credits_balancesnapshot

上游计划快照，**不是**钱包余额，也不是流水。`amount, unit, provider_field, certainty=reported`。未配置适配器时不会产生快照。

### apikeys_apikey

`name, prefix, key_hash(unique), enabled, note, expires_at, last_used_at, request_count`。明文只在创建响应出现一次。

### models_manager_upstreammodel

只保存发现接口或成功转发回显的 model id。`UNIQUE(region, model_id)`。`enabled`、`protocols`（JSON）、`source`（`discovery` / `observed`）、`last_used_at`。没有来源就不插入。

### requestlogs_requestlog

`id` UUID 即 request_id，唯一。`api_key_id`、`account_id`、`region`、`protocol`、`endpoint`、`model`、`resolved_model`、`http_status`、`latency_ms`、`stream`、`input_tokens`、`output_tokens`、`consumed_credits`（可空，无核实消耗时为空）、`ledger_id`、`error_message`、`headers`（脱敏 JSON）、`client_ip`、`created_at`。索引：`(region, created_at)`、`created_at`。不存请求体。

### systemsettings_setting

单行 JSON：`general`、`checkin`、`api`、`account`。敏感项不进这个表，只走环境变量。

### systemsettings_auditlog

管理端写操作：`actor, action, target, created_at`。不记录凭证。

### gateway 运行态

不单独建内存表。`started_at` 由进程启动时写入 `Setting` 的运行段落，重启即更新。协议开关、监听地址来自 settings。

## 索引与分页

列表统一 `limit`（1–200）+ `offset`，排序白名单。日志、流水按时间倒序并限制单页，避免仪表盘重复全表扫描：仪表盘用按日聚合的计数查询，时间范围由参数限制。
