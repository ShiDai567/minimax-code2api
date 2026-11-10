# 后端 API 与数据语义

以仓库根目录的 [API_SPEC.md](../API_SPEC.md) 为准。本文只记录使用时容易误解的约定。

管理接口在 `/api/v1/`，使用 `Authorization: Bearer <ADMIN_TOKEN>`，或用 `CONSOLE_PASSWORD` 登录后拿到的签名令牌。网关接口使用管理界面创建的 API Key。两种凭证不通用。`/health` 不需要认证。

成功响应是 `{"success": true, "source": "live", "fetchedAt": <毫秒时间戳>, "data": ...}`。`source: "live"` 只表示数据来自本服务的数据库，不表示已经和上游核对过。错误响应是 `{"detail": "...", "error": {"code": "..."}}`。

## 容易混淆的地方

- 国内版和国际版分开查询。账号、分组列表必须带 `region=cn` 或 `region=global`，只有仪表盘跨区域汇总。
- 签到成功不等于积分到账。签到记录的 `arrival` 只有在余额同步的差额与奖励一致时才是 `credited`。
- 未同步的余额是 `null`，不是 0。界面应显示“未知”。
- 余额同步和模型发现没有内置地址。未配置 `BALANCE_ADAPTERS` 或 `MODEL_DISCOVERY_URLS` 时返回明确错误，不返回猜测值。
- 有签到、积分或请求记录的账号不能删除，只能停用。有请求记录的 API Key 同样只能停用。
- API Key 明文只在创建响应里出现一次，数据库只存 SHA-256 摘要。日志不保存请求体，认证头的值已脱敏。
