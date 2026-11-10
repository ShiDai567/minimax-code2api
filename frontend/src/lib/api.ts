import type { Region } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8045";
const TOKEN_KEY = "m2a-token";

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code = "REQUEST_FAILED") {
    super(message);
    this.name = "ApiError";
  }
}

export interface Envelope<T> {
  success: boolean;
  source: "live";
  fetchedAt: number;
  data: T;
}

export interface Page<T> {
  items: T[];
  total: number;
}

type Query = Record<string, string | number | undefined | null>;

function queryString(query?: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function readToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function writeToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.dispatchEvent(new Event("m2a-auth"));
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event("m2a-auth"));
}

export class Code2ApiClient {
  constructor(private readonly token = readToken()) {}

  private async request<T>(path: string, init: RequestInit = {}, auth = true): Promise<Envelope<T>> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (auth && this.token) headers.set("Authorization", `Bearer ${this.token}`);
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
    } catch {
      throw new ApiError("无法连接后端，请确认服务已启动", 0, "NETWORK");
    }
    if (response.status === 204) return { success: true, source: "live", fetchedAt: Date.now(), data: undefined as T };
    const body = await response.json().catch(() => null);
    if (!response.ok || !body || body.success === false) {
      const detail = typeof body?.detail === "string"
        ? body.detail
        : typeof body?.data?.failReason === "string"
          ? body.data.failReason
          : `请求失败（${response.status}）`;
      throw new ApiError(detail, response.status, body?.error?.code ?? "REQUEST_FAILED");
    }
    return body as Envelope<T>;
  }

  private get<T>(path: string, query?: Query) {
    return this.request<T>(`${path}${queryString(query)}`);
  }

  private send<T>(path: string, method: string, payload?: unknown) {
    return this.request<T>(path, { method, body: payload === undefined ? undefined : JSON.stringify(payload) });
  }

  health() {
    return this.request<{ status: string; version: string }>("/health", {}, false);
  }

  capabilities() {
    return this.get<Record<string, boolean>>("/api/v1/capabilities/");
  }

  login(password: string) {
    return this.request<{ token: string; expiresAt: number }>(
      "/api/v1/auth/login/",
      { method: "POST", body: JSON.stringify({ password }) },
      false,
    );
  }

  dashboard(range: "24h" | "7d" | "30d" = "24h") {
    return this.get<Record<string, unknown>>("/api/v1/dashboard/", { range });
  }

  accounts(region: Region, query: Query = {}) {
    return this.get<Page<Record<string, unknown>>>("/api/v1/accounts/", { region, ...query });
  }

  createAccount(input: Record<string, unknown>) {
    return this.send<Record<string, unknown>>("/api/v1/accounts/", "POST", input);
  }

  updateAccount(id: string, input: Record<string, unknown>) {
    return this.send<Record<string, unknown>>(`/api/v1/accounts/${id}/`, "PATCH", input);
  }

  deleteAccount(id: string) {
    return this.send<{ deleted: boolean }>(`/api/v1/accounts/${id}/`, "DELETE");
  }

  bulkDelete(region: Region, accountIds: number[]) {
    return this.send<{ deleted: number; blocked: number[] }>("/api/v1/accounts/bulk-delete/", "POST", { region, account_ids: accountIds });
  }

  verifyAccount(id: string, model: string) {
    return this.send<Record<string, unknown>>(`/api/v1/accounts/${id}/verify/`, "POST", { model });
  }

  checkinAccount(id: string) {
    return this.send<Record<string, unknown>>(`/api/v1/accounts/${id}/checkin/`, "POST", {});
  }

  syncCredits(id: string) {
    return this.send<Record<string, unknown>>(`/api/v1/accounts/${id}/sync-credits/`, "POST", {});
  }

  setAccountEnabled(id: string, enabled: boolean) {
    return this.send<Record<string, unknown>>(`/api/v1/accounts/${id}/${enabled ? "enable" : "disable"}/`, "POST", {});
  }

  groups(region: Region, search = "") {
    return this.get<Page<Record<string, unknown>>>("/api/v1/groups/", { region, search });
  }

  createGroup(input: { region: Region; name: string; description?: string; strategy?: string }) {
    return this.send<Record<string, unknown>>("/api/v1/groups/", "POST", input);
  }

  updateGroup(id: string, input: Record<string, unknown>) {
    return this.send<Record<string, unknown>>(`/api/v1/groups/${id}/`, "PATCH", input);
  }

  deleteGroup(id: string) {
    return this.send<{ deleted: boolean }>(`/api/v1/groups/${id}/`, "DELETE");
  }

  checkinRecords(region?: Region, status?: string) {
    return this.get<Page<Record<string, unknown>>>("/api/v1/checkin/records/", { region, status });
  }

  checkinSummary() {
    return this.get<Record<string, number>>("/api/v1/checkin/summary/");
  }

  createCheckinJob(body: { region?: Region; scope?: string; account_ids?: number[]; trigger?: string }) {
    return this.send<Record<string, unknown>>("/api/v1/checkin/jobs/", "POST", body);
  }

  checkinJob(id: string) {
    return this.get<Record<string, unknown>>(`/api/v1/checkin/jobs/${id}/`);
  }

  credits(region?: Region, type?: string) {
    return this.get<Page<Record<string, unknown>>>("/api/v1/credits/", { region, type });
  }

  creditSummary(region?: Region) {
    return this.get<Record<string, number>>("/api/v1/credits/summary/", { region });
  }

  async exportCredits(region?: Region) {
    const headers = new Headers();
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    const response = await fetch(`${API_BASE_URL}/api/v1/credits/export/${queryString({ region })}`, { headers });
    if (!response.ok) throw new ApiError("导出失败", response.status);
    return response.blob();
  }

  keys(search = "") {
    return this.get<Page<Record<string, unknown>>>("/api/v1/keys/", { search });
  }

  createKey(input: { name: string; note?: string }) {
    return this.send<{ key: Record<string, unknown>; secret: string }>("/api/v1/keys/", "POST", input);
  }

  updateKey(id: string, input: Record<string, unknown>) {
    return this.send<Record<string, unknown>>(`/api/v1/keys/${id}/`, "PATCH", input);
  }

  deleteKey(id: string) {
    return this.send<{ deleted: boolean }>(`/api/v1/keys/${id}/`, "DELETE");
  }

  models(region?: Region) {
    return this.get<Page<Record<string, unknown>>>("/api/v1/models/", { region });
  }

  setModelEnabled(id: string, enabled: boolean) {
    return this.send<{ id: string; enabled: boolean }>(`/api/v1/models/${id}/`, "PATCH", { enabled });
  }

  discoverModels(region: Region) {
    return this.send<{ discovered: number }>("/api/v1/models/discover/", "POST", { region });
  }

  logs(query: Query = {}) {
    return this.get<Page<Record<string, unknown>>>("/api/v1/logs/", query);
  }

  gatewayStatus() {
    return this.get<Record<string, unknown>>("/api/v1/gateway/status/");
  }

  gatewayAction(action: "start" | "stop" | "restart") {
    return this.send<Record<string, unknown>>(`/api/v1/gateway/${action}/`, "POST", {});
  }

  runtimeLogs() {
    return this.get<{ items: Record<string, unknown>[] }>("/api/v1/gateway/runtime-logs/");
  }

  settings() {
    return this.get<Record<string, unknown>>("/api/v1/settings/");
  }

  saveSettings(patch: object) {
    return this.send<Record<string, unknown>>("/api/v1/settings/", "PATCH", patch);
  }

  runtime() {
    return this.get<Record<string, unknown>>("/api/v1/runtime/");
  }
}

export function createApiClient(token = readToken()) {
  return new Code2ApiClient(token);
}
