/**
 * Domain model for the MiniMax Code2API console.
 *
 * `cn` = 国内版 (agent.minimax.cn, `mcode login`)
 * `global` = 国际版 (agent.minimax.io, `mcode login --region global`)
 *
 * The two regions never share accounts, credentials or groups.
 */
export type Region = "cn" | "global";

/** Where a payload came from. Everything is `mock` until a real backend adapter exists. */
export type DataSource = "mock" | "live";

export interface Envelope<T> {
  data: T;
  source: DataSource;
  fetchedAt: number;
}

/* ───────────── Accounts ───────────── */

/** Upstream health of an account's credential. `enabled` is tracked separately. */
export type AccountHealth = "healthy" | "error" | "expired";
/** What the UI shows: health folded together with the enabled flag. */
export type AccountStatus = AccountHealth | "disabled";

export interface Account {
  id: string;
  region: Region;
  name: string;
  /** Email or phone used to sign in */
  identifier: string;
  health: AccountHealth;
  healthReason: string | null;
  enabled: boolean;
  /** Always masked. The full credential is never sent to the browser after creation. */
  credentialMasked: string;
  groupId: string | null;
  /** `null` = never synced, value unknown */
  balance: number | null;
  /** When `balance` was last confirmed against upstream */
  balanceSyncedAt: number | null;
  createdAt: number;
  lastCheckinAt: number | null;
  lastActiveAt: number | null;
  note: string;
}

export type CheckinState = "success" | "pending" | "failed" | "not_run";

export interface AccountToday {
  checkin: CheckinState;
  /** Credits that actually reached the ledger today */
  earned: number;
  consumed: number;
  requests: number;
}

export interface AccountRow extends Account {
  status: AccountStatus;
  today: AccountToday;
}

export interface AccountInput {
  region: Region;
  name: string;
  identifier: string;
  /** Plain credential, only sent on create / replace */
  credential?: string;
  groupId: string | null;
  note: string;
}

export interface AccountGroup {
  id: string;
  region: Region;
  name: string;
  description: string;
  createdAt: number;
}

export type GroupStrategy = "round_robin" | "most_credits" | "recent_active" | "least_used";

export interface AccountGroupRow extends AccountGroup {
  strategy: GroupStrategy;
  accountCount: number;
  healthyCount: number;
  /** `null` until a balance adapter confirms it. */
  balance: number | null;
}

/* ───────────── Check-in & credits ───────────── */

export type CheckinTrigger = "schedule" | "manual" | "batch";
/**
 * A successful check-in does not mean credits arrived.
 * `credited` = ledger entry exists, `pending` = waiting for balance sync, `unknown` = could not confirm.
 */
export type CreditArrival = "credited" | "pending" | "unknown";

export interface CheckinRecord {
  id: string;
  accountId: string;
  region: Region;
  at: number;
  result: "success" | "failed";
  /** Credits the upstream reported for this check-in, `null` if not reported */
  reward: number | null;
  arrival: CreditArrival | null;
  ledgerId: string | null;
  failReason: string | null;
  trigger: CheckinTrigger;
}

export type LedgerType = "checkin" | "api_usage" | "adjustment";

export interface LedgerEntry {
  id: string;
  accountId: string;
  region: Region;
  at: number;
  type: LedgerType;
  /** Positive = earned, negative = consumed */
  delta: number;
  balanceBefore: number;
  balanceAfter: number;
  requestId: string | null;
  checkinId: string | null;
  note: string;
}

export interface SchedulerState {
  enabled: boolean;
  /** HH:mm in the configured timezone */
  time: string;
  regions: Region[];
  lastRunAt: number | null;
  lastRunResult: { success: number; failed: number; skipped: number } | null;
  nextRunAt: number | null;
}

export interface CheckinOutcome {
  accountId: string;
  status: "success" | "failed" | "skipped";
  reward: number | null;
  arrival: CreditArrival | null;
  message: string;
}

/* ───────────── Gateway ───────────── */

export type Protocol = "anthropic" | "openai_chat" | "openai_responses";

export interface RequestLog {
  id: string;
  at: number;
  apiKeyId: string | null;
  protocol: Protocol;
  endpoint: string;
  /** Model name the client sent */
  model: string;
  /** Model actually forwarded upstream after alias / default mapping */
  resolvedModel: string;
  accountId: string | null;
  region: Region | null;
  status: "success" | "error";
  httpStatus: number;
  latencyMs: number;
  /** `null` when the upstream did not report usage */
  credits: number | null;
  ledgerId: string | null;
  stream: boolean;
  inputTokens: number | null;
  outputTokens: number | null;
  errorMessage: string | null;
  /** Already masked server-side */
  headers: Record<string, string>;
  clientIp: string;
}

export interface ApiKey {
  id: string;
  name: string;
  /** e.g. `sk-m2a-3f9c••••••••a1b2` */
  masked: string;
  enabled: boolean;
  createdAt: number;
  lastUsedAt: number | null;
  requestCount: number;
  note: string;
}

export interface ApiKeyCreated {
  key: ApiKey;
  /** Shown exactly once */
  secret: string;
}

export interface ModelInfo {
  id: string;
  displayName: string;
  regions: Region[];
  protocols: Protocol[];
  enabled: boolean;
  lastUsedAt: number | null;
  requests24h: number;
}

export type ServiceState = "running" | "stopped" | "starting" | "stopping";

export interface GatewayProtocolStat {
  protocol: Protocol;
  name: string;
  method: "POST";
  endpoint: string;
  enabled: boolean;
  requests: number;
  lastCalledAt: number | null;
}

export interface GatewayStatus {
  state: ServiceState;
  host: string;
  port: number;
  startedAt: number | null;
  inflight: number;
  totalRequests: number;
  successRate: number | null;
  avgLatencyMs: number | null;
  errors24h: number;
  version: string;
  protocols: GatewayProtocolStat[];
  auxEndpoints: { method: "GET" | "POST"; path: string; description: string }[];
}

export interface RuntimeLogLine {
  id: string;
  at: number;
  level: "debug" | "info" | "warn" | "error";
  message: string;
}

/* ───────────── Activity / status ───────────── */

export type ActivityKind =
  | "checkin_success"
  | "checkin_failed"
  | "credit_change"
  | "request_success"
  | "request_failed"
  | "auth_error";

export interface ActivityEvent {
  id: string;
  at: number;
  kind: ActivityKind;
  accountId: string | null;
  region: Region | null;
  title: string;
  detail: string;
  read: boolean;
}

export type ComponentHealth = "operational" | "degraded" | "down" | "unknown";

export interface RuntimeComponent {
  id: string;
  name: string;
  description: string;
  health: ComponentHealth;
  latencyMs: number | null;
  checkedAt: number;
  detail: string;
}

export interface SystemInfo {
  version: string;
  nodeVersion: string | null;
  platform: string | null;
  startedAt: number | null;
  dataSource: DataSource;
  memoryMb: number | null;
}

/* ───────────── Settings ───────────── */

export interface Settings {
  general: {
    systemName: string;
    timezone: string;
    language: "zh-CN";
  };
  checkin: {
    auto: boolean;
    time: string;
    regions: Region[];
    retryOnFailure: boolean;
    maxRetries: number;
  };
  api: {
    host: string;
    port: number;
    requireApiKey: boolean;
    timeoutSec: number;
    /** Unknown client model names (gpt-*, claude-*) are mapped to this */
    defaultModel: string;
  };
  account: {
    autoDisableExpired: boolean;
    errorThreshold: number;
    cooldownMinutes: number;
    regionsEnabled: Region[];
  };
}

/* ───────────── Aggregates ───────────── */

export type TrendRange = "24h" | "7d" | "30d";

export interface CreditPoint {
  t: number;
  label: string;
  earned: number;
  consumed: number;
  balance: number;
}

export interface Metric {
  value: number | null;
  previous: number | null;
}

export interface RegionSummary {
  region: Region;
  total: number;
  online: number;
  abnormal: number;
  disabled: number;
  checkedIn: number;
  awaitingCheckin: number;
  balance: number;
  /** False when no account in the region has a confirmed balance. */
  balanceKnown: boolean;
  /** Accounts whose balance is unknown or stale */
  unsyncedBalances: number;
  consumption7d: { label: string; value: number }[];
}

export interface DashboardData {
  metrics: {
    totalAccounts: Metric;
    healthyAccounts: Metric;
    totalBalance: Metric;
    checkinsToday: Metric;
    requestsToday: Metric;
    creditsConsumedToday: Metric;
  };
  regions: RegionSummary[];
  gateway: Pick<
    GatewayStatus,
    "state" | "totalRequests" | "successRate" | "avgLatencyMs" | "inflight" | "errors24h" | "startedAt"
  >;
  activity: ActivityEvent[];
  /** Confirmed ledger movement only. Empty until a balance sync posts entries. */
  trend: CreditPoint[];
}

export interface CreditsSummary {
  totalBalance: number;
  unconfirmedAccounts: number;
  earnedToday: number;
  consumedToday: number;
  earnedAllTime: number;
  consumedAllTime: number;
  certainty: "confirmed";
}

export interface CheckinSummary {
  total: number;
  pending: number;
  success: number;
  failed: number;
  earnedToday: number;
  /** Successful check-ins whose credits have not been confirmed yet */
  awaitingArrival: number;
}

/** What the connected backend can do. The UI hides controls the backend does not support. */
export interface Capabilities {
  serviceControl: boolean;
  protocolToggle: boolean;
  modelToggle: boolean;
  checkin: boolean;
  credits: boolean;
  multiAccount: boolean;
  runtimeLogs: boolean;
  /** True only when MODEL_DISCOVERY_URLS is configured. */
  modelDiscovery: boolean;
  tokenRefresh: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
}
