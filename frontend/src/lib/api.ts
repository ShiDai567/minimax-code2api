const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8045";

export interface ApiPage<T> {
  items: T[];
  total: number;
  source: "live";
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export class Code2ApiClient {
  constructor(private readonly adminToken: string) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.adminToken}`,
        ...init.headers,
      },
    });
    if (!response.ok) {
      let message = `Backend request failed (${response.status})`;
      try {
        const body = await response.json();
        message = typeof body.detail === "string" ? body.detail : message;
      } catch {
        // Use the HTTP status as the fallback for non-JSON error responses.
      }
      throw new ApiError(message, response.status);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  health() {
    return this.request<{ status: string; version: string; capabilities: Record<string, string> }>("/health", { headers: {} });
  }

  capabilities() {
    return this.request<{ data: Record<string, boolean | string>; source: "live" }>("/api/v1/capabilities");
  }

  dashboard() {
    return this.request<Record<string, unknown>>("/api/v1/dashboard");
  }

  accounts(region?: "cn" | "global") {
    return this.request<ApiPage<Record<string, unknown>>>(`/api/v1/accounts${region ? `?region=${region}` : ""}`);
  }

  createAccount(input: { region: "cn" | "global"; name: string; identifier: string; credential: string; real_user_id?: string; group_id?: number | null; note?: string }) {
    return this.request<Record<string, unknown>>("/api/v1/accounts", { method: "POST", body: JSON.stringify(input) });
  }

  updateAccount(id: string, input: Record<string, unknown>) {
    return this.request<Record<string, unknown>>(`/api/v1/accounts/${id}`, { method: "PATCH", body: JSON.stringify(input) });
  }

  deleteAccount(id: string) {
    return this.request<void>(`/api/v1/accounts/${id}`, { method: "DELETE" });
  }

  groups(region?: "cn" | "global") {
    return this.request<ApiPage<Record<string, unknown>>>(`/api/v1/groups${region ? `?region=${region}` : ""}`);
  }

  keys() {
    return this.request<ApiPage<Record<string, unknown>>>("/api/v1/keys");
  }

  createKey(input: { name: string; note?: string; permissions?: string[] }) {
    return this.request<{ key: Record<string, unknown>; secret: string }>("/api/v1/keys", { method: "POST", body: JSON.stringify(input) });
  }

  logs(limit = 50, offset = 0) {
    return this.request<ApiPage<Record<string, unknown>>>(`/api/v1/logs?limit=${limit}&offset=${offset}`);
  }

  credits() {
    return this.request<{ items: Record<string, unknown>[]; source: "live"; balanceSource: "unknown" }>("/api/v1/credits");
  }

  checkin(accountId: string) {
    return this.request<Record<string, unknown>>(`/api/v1/checkin/run?account_id=${accountId}`, { method: "POST" });
  }

  syncBalance(accountId: string) {
    return this.request<Record<string, unknown>>(`/api/v1/accounts/${accountId}/balance-sync`, { method: "POST" });
  }
}

export function createApiClient(adminToken: string) {
  return new Code2ApiClient(adminToken);
}
