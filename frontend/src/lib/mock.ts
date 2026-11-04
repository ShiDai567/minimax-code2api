import type { AccountRow, DashboardData, Region, ActivityEvent, RequestLog, LedgerEntry } from "./types";

const now = Date.now();
const day = 86_400_000;

export const accounts: AccountRow[] = [
  { id: "cn-01", region: "cn", name: "研发主账号", identifier: "dev@example.com", health: "healthy", healthReason: null, enabled: true, credentialMasked: "lease ·••••7a2c", groupId: "cn-main", balance: 12840, balanceSyncedAt: now - 18 * 60_000, createdAt: now - 28 * day, lastCheckinAt: now - 3 * 60 * 60_000, lastActiveAt: now - 6 * 60_000, note: "主力路由池", status: "healthy", today: { checkin: "success", earned: 420, consumed: 860, requests: 182 } },
  { id: "cn-02", region: "cn", name: "备用账号 A", identifier: "backup-a@example.com", health: "healthy", healthReason: null, enabled: true, credentialMasked: "lease ·••••c921", groupId: "cn-main", balance: 9630, balanceSyncedAt: now - 42 * 60_000, createdAt: now - 24 * day, lastCheckinAt: now - 4 * 60 * 60_000, lastActiveAt: now - 22 * 60_000, note: "", status: "healthy", today: { checkin: "success", earned: 380, consumed: 640, requests: 124 } },
  { id: "cn-03", region: "cn", name: "实验账号", identifier: "lab@example.com", health: "error", healthReason: "上游认证失效，等待重新登录", enabled: true, credentialMasked: "lease ·••••19ef", groupId: "cn-lab", balance: null, balanceSyncedAt: now - 2 * day, createdAt: now - 16 * day, lastCheckinAt: now - 2 * day, lastActiveAt: now - 2 * day, note: "", status: "error", today: { checkin: "failed", earned: 0, consumed: 0, requests: 0 } },
  { id: "io-01", region: "global", name: "Global Primary", identifier: "global@example.com", health: "healthy", healthReason: null, enabled: true, credentialMasked: "lease ·••••2d04", groupId: "io-main", balance: 11290, balanceSyncedAt: now - 25 * 60_000, createdAt: now - 30 * day, lastCheckinAt: now - 5 * 60 * 60_000, lastActiveAt: now - 2 * 60_000, note: "国际版主力路由池", status: "healthy", today: { checkin: "success", earned: 510, consumed: 920, requests: 206 } },
  { id: "io-02", region: "global", name: "Global Standby", identifier: "standby@example.com", health: "expired", healthReason: "桌面端登录态已过期", enabled: true, credentialMasked: "lease ·••••84bd", groupId: "io-main", balance: 7420, balanceSyncedAt: now - 5 * day, createdAt: now - 19 * day, lastCheckinAt: now - 5 * day, lastActiveAt: now - 5 * day, note: "", status: "expired", today: { checkin: "failed", earned: 0, consumed: 0, requests: 0 } },
  { id: "io-03", region: "global", name: "低优先级账号", identifier: "low-priority@example.com", health: "healthy", healthReason: null, enabled: false, credentialMasked: "lease ·••••50a1", groupId: "io-low", balance: 3180, balanceSyncedAt: now - day, createdAt: now - 11 * day, lastCheckinAt: null, lastActiveAt: now - 3 * day, note: "暂时停用", status: "disabled", today: { checkin: "not_run", earned: 0, consumed: 0, requests: 0 } },
];

const activities: ActivityEvent[] = [
  { id: "a1", at: now - 6 * 60_000, kind: "request_success", accountId: "cn-01", region: "cn", title: "API 请求成功", detail: "Anthropic Messages · MiniMax-M3 · 842ms", read: false },
  { id: "a2", at: now - 28 * 60_000, kind: "checkin_success", accountId: "io-01", region: "global", title: "国际版签到成功", detail: "积分到账状态：已确认 · +510", read: false },
  { id: "a3", at: now - 52 * 60_000, kind: "auth_error", accountId: "cn-03", region: "cn", title: "账号认证异常", detail: "实验账号 · 上游认证失效", read: false },
  { id: "a4", at: now - 2 * 60 * 60_000, kind: "credit_change", accountId: "cn-02", region: "cn", title: "积分发生变化", detail: "签到到账 · +380", read: true },
  { id: "a5", at: now - 3 * 60 * 60_000, kind: "request_failed", accountId: "io-02", region: "global", title: "API 请求失败", detail: "上游返回 401 · 账号登录态已过期", read: true },
];

export const requestLogs: RequestLog[] = [
  { id: "req_8a21f1", at: now - 6 * 60_000, apiKeyId: "key-01", protocol: "anthropic", endpoint: "/v1/messages", model: "MiniMax-M3", resolvedModel: "MiniMax-M3", accountId: "cn-01", region: "cn", status: "success", httpStatus: 200, latencyMs: 842, credits: 12, ledgerId: "led-1", stream: true, inputTokens: 1830, outputTokens: 692, errorMessage: null, headers: { authorization: "Bearer ••••", "x-api-key": "sk-••••" }, clientIp: "127.0.0.1" },
  { id: "req_8a20cc", at: now - 21 * 60_000, apiKeyId: "key-02", protocol: "openai_chat", endpoint: "/v1/chat/completions", model: "gpt-4o", resolvedModel: "MiniMax-M3", accountId: "cn-02", region: "cn", status: "success", httpStatus: 200, latencyMs: 710, credits: 8, ledgerId: "led-2", stream: false, inputTokens: 1120, outputTokens: 401, errorMessage: null, headers: { authorization: "Bearer ••••" }, clientIp: "127.0.0.1" },
  { id: "req_8a1d10", at: now - 3 * 60 * 60_000, apiKeyId: "key-01", protocol: "anthropic", endpoint: "/v1/messages", model: "MiniMax-M3", resolvedModel: "MiniMax-M3", accountId: "io-02", region: "global", status: "error", httpStatus: 401, latencyMs: 204, credits: 0, ledgerId: null, stream: true, inputTokens: null, outputTokens: null, errorMessage: "upstream authentication expired", headers: { authorization: "Bearer ••••" }, clientIp: "127.0.0.1" },
];

export const ledger: LedgerEntry[] = [
  { id: "led-1", accountId: "cn-01", region: "cn", at: now - 6 * 60_000, type: "api_usage", delta: -12, balanceBefore: 12852, balanceAfter: 12840, requestId: "req_8a21f1", checkinId: null, note: "MiniMax-M3 API 消耗" },
  { id: "led-2", accountId: "cn-02", region: "cn", at: now - 21 * 60_000, type: "api_usage", delta: -8, balanceBefore: 9638, balanceAfter: 9630, requestId: "req_8a20cc", checkinId: null, note: "MiniMax-M3 API 消耗" },
  { id: "led-3", accountId: "io-01", region: "global", at: now - 28 * 60_000, type: "checkin", delta: 510, balanceBefore: 10780, balanceAfter: 11290, requestId: null, checkinId: "check-io-01", note: "签到积分到账" },
];

export const models = ["MiniMax-M3", "MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7", "MiniMax-M2.7-highspeed"];

export function dashboard(): DashboardData {
  const total = accounts.length;
  const healthy = accounts.filter((a) => a.enabled && a.health === "healthy").length;
  const balance = accounts.reduce((sum, a) => sum + (a.balance ?? 0), 0);
  const requests = accounts.reduce((sum, a) => sum + a.today.requests, 0);
  return {
    metrics: { totalAccounts: { value: total, previous: total - 1 }, healthyAccounts: { value: healthy, previous: healthy }, totalBalance: { value: balance, previous: balance - 642 }, checkinsToday: { value: accounts.filter((a) => a.today.checkin === "success").length, previous: 3 }, requestsToday: { value: requests, previous: requests - 82 }, creditsConsumedToday: { value: 2420, previous: 2184 } },
    regions: (["cn", "global"] as Region[]).map((region) => { const rows = accounts.filter((a) => a.region === region); return { region, total: rows.length, online: rows.filter((a) => a.health === "healthy" && a.enabled).length, abnormal: rows.filter((a) => a.health !== "healthy").length, disabled: rows.filter((a) => !a.enabled).length, checkedIn: rows.filter((a) => a.today.checkin === "success").length, awaitingCheckin: rows.filter((a) => a.today.checkin === "not_run").length, balance: rows.reduce((sum, a) => sum + (a.balance ?? 0), 0), unsyncedBalances: rows.filter((a) => a.balance === null).length, consumption7d: ["周一", "周二", "周三", "周四", "周五", "周六", "今天"].map((label, i) => ({ label, value: (region === "cn" ? 360 : 420) + i * 36 - (i === 5 ? 80 : 0) })) }; }),
    gateway: { state: "running", totalRequests: 14862, successRate: 98.4, avgLatencyMs: 682, inflight: 3, errors24h: 42, startedAt: now - 6 * day - 3 * 60 * 60_000 }, activity: activities,
  };
}

export const navGroups = [
  { label: "概览", items: [{ label: "仪表盘", href: "/", icon: "layout" }] },
  { label: "账号管理", items: [{ label: "国内版账号", href: "/accounts/cn", icon: "users" }, { label: "国际版账号", href: "/accounts/global", icon: "globe" }, { label: "账号分组", href: "/accounts/groups", icon: "layers" }] },
  { label: "签到与积分", items: [{ label: "签到管理", href: "/checkin", icon: "calendar" }, { label: "积分记录", href: "/credits", icon: "coins" }] },
  { label: "API 网关", items: [{ label: "API 服务", href: "/gateway", icon: "server" }, { label: "API Keys", href: "/gateway/keys", icon: "key" }, { label: "模型管理", href: "/gateway/models", icon: "boxes" }, { label: "请求日志", href: "/gateway/logs", icon: "logs" }] },
  { label: "系统", items: [{ label: "系统设置", href: "/settings", icon: "settings" }, { label: "运行状态", href: "/status", icon: "activity" }] },
];

export function formatNumber(value: number | null) { return value === null ? "未知" : new Intl.NumberFormat("zh-CN").format(value); }
export function formatTime(value: number | null) { return value ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(value) : "—"; }
export function formatRelative(value: number) { const minutes = Math.max(1, Math.round((now - value) / 60_000)); return minutes < 60 ? `${minutes} 分钟前` : `${Math.round(minutes / 60)} 小时前`; }
