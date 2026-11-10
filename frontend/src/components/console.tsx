"use client";

import type { ReactNode } from "react";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { toast, Toaster } from "sonner";
import {
  Activity, Bell, Boxes, CalendarCheck, Check, CircleAlert, CircleCheck, CircleDashed,
  Coins, Copy, Globe, HeartPulse, KeyRound, Layers, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search,
  Server, Settings, ShieldAlert, Sun, Users, X, Zap,
} from "lucide-react";
import { clearToken, readToken, writeToken } from "@/lib/api";
import { client, messageOf, useLive } from "@/lib/live";
import { navGroups } from "@/lib/nav";
import type {
  AccountGroupRow, AccountRow, ActivityEvent, ApiKey, Capabilities, CheckinRecord, CreditsSummary,
  DashboardData, GatewayStatus, LedgerEntry, ModelInfo, Region, RequestLog, RuntimeLogLine, Settings as SettingsModel,
} from "@/lib/types";

const icons = {
  layout: Activity, users: Users, globe: Globe, layers: Layers, calendar: CalendarCheck, coins: Coins,
  server: Server, key: KeyRound, boxes: Boxes, logs: Activity, settings: Settings, activity: HeartPulse,
} as const;
type IconName = keyof typeof icons;

function Icon({ name, size = 17 }: { name: IconName; size?: number }) {
  const Component = icons[name];
  return <Component size={size} strokeWidth={1.8} />;
}

function getView(path: string) {
  if (path === "/") return "dashboard";
  if (path.includes("accounts/groups")) return "groups";
  if (path.includes("accounts")) return "accounts";
  if (path.includes("checkin")) return "checkin";
  if (path.includes("credits")) return "credits";
  if (path.includes("gateway/keys")) return "keys";
  if (path.includes("gateway/models")) return "models";
  if (path.includes("gateway/logs")) return "logs";
  if (path.includes("gateway")) return "gateway";
  if (path.includes("settings")) return "settings";
  return "status";
}

function statusLabel(status: AccountRow["status"]) {
  return { healthy: "正常", error: "异常", expired: "已过期", disabled: "已停用" }[status];
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "未知" : new Intl.NumberFormat("zh-CN").format(value);
}

function formatRelative(value: number | null) {
  if (!value) return "—";
  const minutes = Math.max(1, Math.round((Date.now() - value) / 60_000));
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / 1440)} 天前`;
}

function as<T>(value: unknown) {
  return value as T;
}

async function run(label: string, action: () => Promise<unknown>, done: string) {
  const id = toast.loading(label);
  try {
    const result = await action();
    toast.success(done, { id });
    return result;
  } catch (reason) {
    toast.error(messageOf(reason), { id });
    return null;
  }
}

export default function Console() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-bg" />}>
      <Toaster position="top-center" theme="system" />
      <ConsoleInner />
    </Suspense>
  );
}

function ConsoleInner() {
  const path = usePathname();
  const view = getView(path);
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [dark, setDark] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const sync = () => {
      setAuthed(Boolean(readToken()));
      setDark(document.documentElement.getAttribute("data-theme") === "dark");
    };
    sync();
    window.addEventListener("m2a-auth", sync);
    return () => window.removeEventListener("m2a-auth", sync);
  }, []);

  const title = navGroups.flatMap((group) => group.items).find((item) => item.href === path)?.label
    ?? (view === "accounts" ? (path.includes("global") ? "国际版账号" : "国内版账号") : "仪表盘");

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
    localStorage.setItem("m2a-theme", next ? "dark" : "light");
  };

  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  return (
    <div className="min-h-screen bg-bg text-ink">
      <aside className={`material-side fixed inset-y-0 left-0 z-40 hidden border-r border-line lg:flex lg:flex-col ${collapsed ? "w-[68px]" : "w-[248px]"}`}>
        <div className="flex h-16 items-center gap-3 px-5">
          <div className="grid size-8 shrink-0 place-items-center rounded-[10px] bg-ink text-bg"><Zap size={17} fill="currentColor" /></div>
          {!collapsed && <div><div className="text-[13px] font-semibold tracking-tight">MiniMax Code2API</div><div className="mt-0.5 text-[10px] text-ink-3">管理控制台</div></div>}
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-5">
              <div className={`mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[.08em] text-ink-3 ${collapsed ? "sr-only" : ""}`}>{group.label}</div>
              {group.items.map((item) => {
                const active = item.href === path || (item.href !== "/" && path.startsWith(item.href));
                return (
                  <Link key={item.href} href={item.href} title={collapsed ? item.label : undefined} className={`mb-0.5 flex h-9 items-center gap-3 rounded-md px-3 text-[13px] ${active ? "bg-fill font-medium text-ink" : "text-ink-2 hover:bg-fill-2 hover:text-ink"}`}>
                    <Icon name={item.icon as IconName} />
                    {!collapsed && <span>{item.label}</span>}
                    {active && !collapsed && <span className="ml-auto size-1.5 rounded-full bg-accent" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className={`border-t border-line p-3 ${collapsed ? "text-center" : ""}`}>
          <div className="mb-2 flex items-center gap-2 text-[11px] text-ink-3"><span className="size-1.5 rounded-full bg-success" />{!collapsed && "实时数据"}</div>
          {!collapsed ? (
            <div className="flex items-center justify-between text-[10px] text-ink-3">
              <button onClick={() => { clearToken(); toast.success("已退出登录"); }} className="hover:text-ink">退出登录</button>
              <button onClick={() => setCollapsed(true)} className="rounded p-1 hover:bg-fill" title="收起导航"><PanelLeftClose size={14} /></button>
            </div>
          ) : <button onClick={() => setCollapsed(false)} className="rounded p-1 text-ink-2 hover:bg-fill" title="展开导航"><PanelLeftOpen size={15} /></button>}
        </div>
      </aside>
      {mobile && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-black/30" onClick={() => setMobile(false)} aria-label="关闭导航" />
          <div className="material-side absolute inset-y-0 left-0 w-[260px] border-r border-line p-3">
            <div className="flex h-14 items-center justify-between px-2"><b>MiniMax Code2API</b><button onClick={() => setMobile(false)}><X size={18} /></button></div>
            {navGroups.flatMap((group) => group.items).map((item) => (
              <Link onClick={() => setMobile(false)} key={item.href} href={item.href} className="flex h-10 items-center gap-3 rounded-md px-3 text-sm text-ink-2 hover:bg-fill"><Icon name={item.icon as IconName} />{item.label}</Link>
            ))}
          </div>
        </div>
      )}
      <div className={`min-h-screen ${collapsed ? "lg:pl-[68px]" : "lg:pl-[248px]"}`}>
        <header className="material-bar sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line px-5 lg:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setMobile(true)} className="rounded-md p-1.5 text-ink-2 hover:bg-fill lg:hidden" title="打开导航"><Menu size={19} /></button>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] text-ink-3"><span>MiniMax Code2API</span><span>/</span><span className="truncate text-ink-2">{title}</span></div>
              <div className="mt-0.5 truncate text-[14px] font-semibold">{title}</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <div className="mr-2 hidden items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-[11px] text-success sm:flex"><span className="size-1.5 rounded-full bg-success" />实时数据</div>
            <button onClick={() => setSearchOpen(!searchOpen)} className="rounded-md p-2 text-ink-2 hover:bg-fill" title="全局搜索"><Search size={17} /></button>
            <button onClick={toggleTheme} className="rounded-md p-2 text-ink-2 hover:bg-fill" title="切换主题">{dark ? <Sun size={17} /> : <Moon size={17} />}</button>
            <button onClick={() => setNotifications(!notifications)} className="rounded-md p-2 text-ink-2 hover:bg-fill" title="通知"><Bell size={17} /></button>
          </div>
        </header>
        {searchOpen && <SearchPanel onClose={() => setSearchOpen(false)} />}
        {notifications && <div className="px-5 pt-4 text-xs text-ink-2 lg:px-7">通知来自仪表盘最近活动，打开仪表盘查看。</div>}
        <main className="px-5 py-6 lg:px-7"><View view={view} path={path} /></main>
      </div>
    </div>
  );
}

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const result = await client().login(password);
      writeToken(result.data.token);
      toast.success("已登录");
      onSuccess();
    } catch (reason) {
      toast.error(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-bg px-4">
      <form onSubmit={(event) => { event.preventDefault(); void submit(); }} className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 shadow-card">
        <div className="mb-5 flex items-center gap-3"><div className="grid size-9 place-items-center rounded-[10px] bg-ink text-bg"><Zap size={18} fill="currentColor" /></div><div><div className="font-semibold">MiniMax Code2API</div><div className="text-xs text-ink-3">输入控制台密码</div></div></div>
        <label className="mb-5 block text-xs"><span className="mb-1.5 block text-ink-2">密码</span><input type="password" autoFocus value={password} onChange={(event) => setPassword(event.target.value)} className="h-9 w-full rounded-md bg-fill-2 px-3 outline-none focus:ring-2 focus:ring-accent" /></label>
        <button disabled={busy || !password} className="h-9 w-full rounded-md bg-accent text-xs font-medium text-white disabled:opacity-60">{busy ? "登录中…" : "登录"}</button>
      </form>
    </div>
  );
}

function SearchPanel({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const matches = navGroups.flatMap((group) => group.items).filter((item) => item.label.includes(query));
  return (
    <div className="border-b border-line bg-surface px-5 py-3 lg:px-7">
      <div className="flex items-center gap-2"><Search size={15} className="text-ink-3" /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索页面" className="h-8 flex-1 bg-transparent text-sm outline-none" /><button onClick={onClose}><X size={15} /></button></div>
      <div className="mt-2 flex flex-wrap gap-2">{matches.map((item) => <Link key={item.href} href={item.href} onClick={onClose} className="rounded-md bg-fill-2 px-2 py-1 text-xs">{item.label}</Link>)}</div>
    </div>
  );
}

function View({ view, path }: { view: string; path: string }) {
  if (view === "dashboard") return <Dashboard />;
  if (view === "accounts") return <Accounts region={path.includes("global") ? "global" : "cn"} />;
  if (view === "groups") return <Groups />;
  if (view === "checkin") return <Checkin />;
  if (view === "credits") return <Credits />;
  if (view === "gateway") return <Gateway />;
  if (view === "keys") return <Keys />;
  if (view === "models") return <Models />;
  if (view === "logs") return <Logs />;
  if (view === "settings") return <SettingsView />;
  return <Status />;
}

function Header({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-6 flex items-end justify-between gap-4"><div><div className="t-overline text-ink-3">{eyebrow}</div><h1 className="mt-1 t-display">{title}</h1>{description && <p className="mt-2 max-w-2xl text-[13px] text-ink-2">{description}</p>}</div>{action}</div>;
}

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border border-line bg-surface shadow-card ${className}`}>{children}</section>;
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "green" | "orange" }) {
  return <Card className="p-4"><div className="flex items-center justify-between"><span className="text-[12px] text-ink-2">{label}</span><span className={`size-1.5 rounded-full ${tone === "green" ? "bg-success" : tone === "orange" ? "bg-warning" : "bg-accent"}`} /></div><strong className="mt-3 block t-metric">{value}</strong></Card>;
}

function RegionBadge({ region }: { region: Region }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ${region === "cn" ? "bg-region-cn-soft text-region-cn" : "bg-region-global-soft text-region-global"}`}><span className="size-1.5 rounded-full bg-current" />{region === "cn" ? "国内版" : "国际版"}</span>;
}

function StatusBadge({ account }: { account: AccountRow }) {
  const tone = account.status === "healthy" ? "bg-success-soft text-success" : account.status === "disabled" ? "bg-neutral-soft text-ink-2" : "bg-danger-soft text-danger";
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ${tone}`}>{account.status === "healthy" ? <CircleCheck size={12} /> : account.status === "disabled" ? <CircleDashed size={12} /> : <ShieldAlert size={12} />}{statusLabel(account.status)}</span>;
}

function Notice({ state }: { state: { loading: boolean; error: string | null; empty?: boolean } }) {
  if (state.loading) return <div className="p-8 text-center text-xs text-ink-3">加载中…</div>;
  if (state.error) return <div className="flex items-center justify-center gap-2 p-8 text-xs text-danger"><CircleAlert size={14} />{state.error}</div>;
  if (state.empty) return <div className="p-8 text-center text-xs text-ink-3">暂无数据</div>;
  return null;
}

function Confirm({ title, detail, onConfirm, onClose }: { title: string; detail: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4">
      <div className="w-full max-w-sm rounded-lg bg-surface p-5 shadow-sheet">
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-2 text-xs text-ink-2">{detail}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="h-8 rounded-md bg-fill-2 px-3 text-xs">取消</button>
          <button onClick={onConfirm} className="h-8 rounded-md bg-danger px-3 text-xs text-white">确认</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-xs"><span className="mb-1.5 block text-ink-2">{label}</span>{children}</label>;
}

const inputClass = "h-9 w-full rounded-md bg-fill-2 px-3 outline-none focus:ring-2 focus:ring-accent";

function Dashboard() {
  const [range, setRange] = useState<"24h" | "7d" | "30d">("24h");
  const state = useLive(async () => as<DashboardData>((await client().dashboard(range)).data), [range]);
  const data = state.data;
  return (
    <>
      <Header eyebrow="Overview" title="仪表盘" description="网关、账号与积分的实时概览。余额只在上游已确认时显示。" action={<Link href="/status" className="flex h-9 items-center gap-2 rounded-md bg-ink px-3.5 text-xs font-medium text-bg"><Activity size={15} />查看运行状态</Link>} />
      <Notice state={state} />
      {data && (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <Metric label="总账号数" value={formatNumber(data.metrics.totalAccounts.value)} />
            <Metric label="正常账号" value={formatNumber(data.metrics.healthyAccounts.value)} tone="green" />
            <Metric label="总积分余额" value={formatNumber(data.metrics.totalBalance.value)} />
            <Metric label="今日签到" value={formatNumber(data.metrics.checkinsToday.value)} tone="green" />
            <Metric label="今日请求量" value={formatNumber(data.metrics.requestsToday.value)} />
            <Metric label="今日积分消耗" value={formatNumber(data.metrics.creditsConsumedToday.value)} tone="orange" />
          </div>
          <div className="grid gap-4 xl:grid-cols-[1.45fr_1fr]">
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-line px-5 py-4"><div><h2 className="t-title">账号区域概览</h2><p className="mt-1 text-xs text-ink-2">国内版与国际版保持独立统计</p></div></div>
              <div className="grid divide-y divide-line md:grid-cols-2 md:divide-x md:divide-y-0">{data.regions.map((region) => <RegionPanel key={region.region} data={region} />)}</div>
            </Card>
            <Card>
              <div className="border-b border-line px-5 py-4"><h2 className="t-title">API 服务状态</h2></div>
              <div className="grid grid-cols-2 gap-px bg-line">
                {[["状态", data.gateway.state === "running" ? "运行中" : "已停止"], ["成功率", data.gateway.successRate === null ? "未知" : `${data.gateway.successRate}%`], ["平均响应", data.gateway.avgLatencyMs === null ? "未知" : `${data.gateway.avgLatencyMs} ms`], ["24 小时错误", String(data.gateway.errors24h)]].map(([label, value]) => <div className="bg-surface p-4" key={label}><div className="text-xs text-ink-2">{label}</div><div className="mt-2 text-lg font-semibold">{value}</div></div>)}
              </div>
            </Card>
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <CreditChart points={data.trend ?? []} range={range} onRange={setRange} />
            <ActivityFeed items={data.activity} />
          </div>
        </>
      )}
    </>
  );
}

function RegionPanel({ data }: { data: DashboardData["regions"][number] }) {
  const max = Math.max(1, ...data.consumption7d.map((item) => item.value));
  return (
    <div className="p-5">
      <div className="flex items-center justify-between"><RegionBadge region={data.region} /><span className="text-xs text-ink-2">{data.online}/{data.total} 正常</span></div>
      <div className="mt-5 flex items-end justify-between"><div><div className="text-xs text-ink-2">已确认积分余额</div><div className="mt-1 text-2xl font-semibold tnum tracking-tight">{data.balanceKnown === false ? "未知" : formatNumber(data.balance)}</div></div><div className="text-right text-xs"><div className="text-success">{data.checkedIn} 已签到</div><div className="mt-1 text-ink-3">{data.awaitingCheckin} 待签到</div></div></div>
      <div className="mt-5 flex h-12 items-end gap-1">{data.consumption7d.map((item) => <div key={item.label} className="flex-1 rounded-t-sm bg-accent-soft" style={{ height: `${Math.max(8, (item.value / max) * 100)}%` }} title={`${item.label} ${item.value}`} />)}</div>
      <div className="mt-2 flex justify-between text-[10px] text-ink-3"><span>近 7 日消耗</span><span>{data.unsyncedBalances} 个余额未同步</span></div>
    </div>
  );
}

function CreditChart({ points, range, onRange }: { points: { t: number; label: string; earned: number; consumed: number }[]; range: string; onRange: (value: "24h" | "7d" | "30d") => void }) {
  const max = Math.max(1, ...points.map((point) => Math.max(point.earned, point.consumed)));
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between"><div><h2 className="t-title">积分趋势</h2><p className="mt-1 text-xs text-ink-2">只统计已入账的变动</p></div><div className="flex rounded-md bg-fill-2 p-0.5 text-[11px]">{(["24h", "7d", "30d"] as const).map((item) => <button key={item} onClick={() => onRange(item)} className={`rounded px-2 py-1 ${range === item ? "bg-surface font-medium shadow-card" : "text-ink-2"}`}>{item === "24h" ? "24 小时" : item === "7d" ? "7 天" : "30 天"}</button>)}</div></div>
      <div className="mt-7 flex h-44 items-end gap-1.5 border-b border-line">{points.length === 0 && <div className="w-full text-center text-xs text-ink-3">暂无已确认流水</div>}{points.map((point) => <div key={point.t} className="flex flex-1 items-end gap-0.5" title={`${point.label} 获取 ${point.earned} / 消耗 ${point.consumed}`}><div className="flex-1 rounded-t-[3px] bg-success" style={{ height: `${(point.earned / max) * 100}%` }} /><div className="flex-1 rounded-t-[3px] bg-accent" style={{ height: `${(point.consumed / max) * 100}%` }} /></div>)}</div>
    </Card>
  );
}

function ActivityFeed({ items }: { items: ActivityEvent[] }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><h2 className="t-title">最近活动</h2><Link href="/gateway/logs" className="text-xs text-accent">查看日志</Link></div>
      <div className="mt-5 space-y-4">{items.length === 0 && <div className="text-xs text-ink-3">暂无活动</div>}{items.map((item) => <div key={item.id} className="flex gap-3"><div className={`mt-1 grid size-6 shrink-0 place-items-center rounded-full ${item.kind.includes("failed") ? "bg-danger-soft text-danger" : "bg-success-soft text-success"}`}>{item.kind.includes("failed") ? <ShieldAlert size={13} /> : <Check size={13} />}</div><div className="min-w-0 flex-1"><div className="flex justify-between gap-3 text-xs font-medium"><span>{item.title}</span><span className="text-[10px] font-normal text-ink-3">{formatRelative(item.at)}</span></div><div className="mt-1 truncate text-[11px] text-ink-2">{item.detail}</div></div></div>)}</div>
    </Card>
  );
}

function Accounts({ region }: { region: Region }) {
  const [query, setQuery] = useState("");
  const [health, setHealth] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const state = useLive(async () => as<AccountRow[]>((await client().accounts(region, { search: query, health, limit: 100 })).data.items), [region, query, health]);
  const rows = state.data ?? [];

  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  const batchCheckin = async () => {
    let success = 0;
    let failed = 0;
    for (const [index, id] of selected.entries()) {
      setProgress(`签到中 ${index + 1}/${selected.length}`);
      try {
        await client().checkinAccount(id);
        success += 1;
      } catch {
        failed += 1;
      }
    }
    setProgress(null);
    toast.success(`批量签到完成：成功 ${success}，失败 ${failed}`);
    setSelected([]);
    state.reload();
  };

  return (
    <>
      <Header eyebrow="Account Management" title={region === "cn" ? "国内版账号" : "国际版账号"} description={region === "cn" ? "独立管理 agent.minimax.cn 的账号与积分。" : "独立管理 agent.minimax.io 的账号与积分。"} action={<button onClick={() => setCreating(true)} className="h-9 rounded-md bg-accent px-3.5 text-xs font-medium text-white">+ 添加账号</button>} />
      <div className="mb-5 grid gap-3 sm:grid-cols-4">
        <Metric label="账号总数" value={String(rows.length)} />
        <Metric label="正常账号" value={String(rows.filter((row) => row.health === "healthy" && row.enabled).length)} tone="green" />
        <Metric label="今日已签到" value={String(rows.filter((row) => row.today.checkin === "success").length)} tone="green" />
        <Metric label="已确认余额" value={formatNumber(rows.some((row) => row.balance !== null) ? rows.reduce((sum, row) => sum + (row.balance ?? 0), 0) : null)} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-2.5 text-ink-3" size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索账号名称或标识" className="h-9 w-full rounded-md bg-fill-2 pl-9 pr-3 text-xs outline-none focus:ring-2 focus:ring-accent" /></div>
          <select value={health} onChange={(event) => setHealth(event.target.value)} className="h-9 rounded-md bg-fill-2 px-3 text-xs text-ink-2"><option value="">全部状态</option><option value="healthy">正常</option><option value="error">异常</option><option value="expired">已过期</option><option value="unknown">未验证</option></select>
        </div>
        {selected.length > 0 && <div className="flex items-center gap-3 border-b border-line bg-accent-soft px-4 py-2 text-xs"><span>已选 {selected.length} 个账号</span><button onClick={() => void batchCheckin()} className="rounded bg-accent px-2 py-1 text-white">批量签到</button><button onClick={() => setConfirmDelete(true)} className="text-danger">删除</button><button onClick={() => setSelected([])} className="text-ink-3">取消</button>{progress && <span className="text-ink-2">{progress}</span>}</div>}
        <Notice state={{ ...state, empty: !state.loading && rows.length === 0 }} />
        {rows.length > 0 && (
          <div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left text-xs"><thead><tr className="border-b border-line text-ink-3"><th className="px-4 py-3" /><th className="px-3 py-3 font-medium">账号</th><th className="px-3 py-3 font-medium">状态</th><th className="px-3 py-3 font-medium">今日签到</th><th className="px-3 py-3 font-medium">余额</th><th className="px-5 py-3 font-medium">操作</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.id} className="border-b border-line last:border-0"><td className="px-4 py-4"><input type="checkbox" checked={selected.includes(row.id)} onChange={() => toggle(row.id)} aria-label={`选择 ${row.name}`} /></td><td className="px-3 py-4"><div className="font-medium">{row.name}</div><div className="mt-1 text-[11px] text-ink-3">{row.identifier} · {row.credentialMasked}</div></td><td className="px-3 py-4"><StatusBadge account={row} /></td><td className="px-3 py-4">{row.today.checkin === "success" ? "已签到" : row.today.checkin === "failed" ? "失败" : row.today.checkin === "pending" ? "进行中" : "未执行"}</td><td className="px-3 py-4 tnum">{formatNumber(row.balance)}</td><td className="px-5 py-4"><div className="flex gap-2"><button onClick={() => void run("签到中", () => client().checkinAccount(row.id), "签到已执行").then(() => state.reload())} className="text-accent">签到</button><button onClick={() => void run("同步余额", () => client().syncCredits(row.id), "已同步").then(() => state.reload())} className="text-ink-2">同步</button><button onClick={() => void run(row.enabled ? "停用中" : "启用中", () => client().setAccountEnabled(row.id, !row.enabled), "已更新").then(() => state.reload())} className="text-ink-2">{row.enabled ? "停用" : "启用"}</button></div></td></tr>)}</tbody>
          </table></div>
        )}
      </Card>
      {creating && <AccountForm region={region} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); state.reload(); }} />}
      {confirmDelete && <Confirm title="删除选中账号" detail="有签到或积分记录的账号会被拒绝删除，只能停用。" onClose={() => setConfirmDelete(false)} onConfirm={() => { setConfirmDelete(false); void run("删除中", () => client().bulkDelete(region, selected.map(Number)), "删除完成").then(() => { setSelected([]); state.reload(); }); }} />}
    </>
  );
}

function AccountForm({ region, onClose, onSaved }: { region: Region; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: "", identifier: "", credential: "", real_user_id: "", note: "", model: "" });
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: event.target.value });
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4">
      <form onSubmit={(event) => { event.preventDefault(); void run("添加中", () => client().createAccount({ ...form, region, model: form.model || undefined }), "账号已添加").then((result) => result && onSaved()); }} className="w-full max-w-md space-y-3 rounded-lg bg-surface p-5 shadow-sheet">
        <div className="flex items-center justify-between"><h2 className="font-semibold">添加{region === "cn" ? "国内版" : "国际版"}账号</h2><button type="button" onClick={onClose}><X size={16} /></button></div>
        <Field label="名称"><input required value={form.name} onChange={set("name")} className={inputClass} /></Field>
        <Field label="登录标识"><input required value={form.identifier} onChange={set("identifier")} className={inputClass} /></Field>
        <Field label="凭证"><input required value={form.credential} onChange={set("credential")} className={inputClass} /></Field>
        <Field label="real_user_id（签到需要）"><input value={form.real_user_id} onChange={set("real_user_id")} className={inputClass} /></Field>
        <Field label="验证模型（可选）"><input value={form.model} onChange={set("model")} placeholder="留空则不立即验证" className={inputClass} /></Field>
        <Field label="备注"><input value={form.note} onChange={set("note")} className={inputClass} /></Field>
        <button className="h-9 w-full rounded-md bg-accent text-xs font-medium text-white">保存</button>
      </form>
    </div>
  );
}

function Groups() {
  const [creating, setCreating] = useState(false);
  const cn = useLive(async () => as<AccountGroupRow[]>((await client().groups("cn")).data.items), []);
  const global = useLive(async () => as<AccountGroupRow[]>((await client().groups("global")).data.items), []);
  const groups = [...(cn.data ?? []), ...(global.data ?? [])];
  return (
    <>
      <Header eyebrow="Account Management" title="账号分组" description="分组仅在同一区域内生效，避免国内版与国际版凭证混用。" action={<button onClick={() => setCreating(true)} className="h-9 rounded-md bg-accent px-3.5 text-xs font-medium text-white">+ 新建分组</button>} />
      <Notice state={{ loading: cn.loading || global.loading, error: cn.error ?? global.error, empty: groups.length === 0 }} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{groups.map((group) => <Card key={group.id} className="p-5"><div className="flex items-start justify-between"><RegionBadge region={group.region} /><button onClick={() => void run("删除分组", () => client().deleteGroup(group.id), "已删除").then(() => { cn.reload(); global.reload(); })} className="text-xs text-danger">删除</button></div><h2 className="mt-4 text-base font-semibold">{group.name}</h2><p className="mt-1 text-xs text-ink-2">{group.description || "无描述"} · {strategyLabel(group.strategy)}</p><div className="mt-5 text-xl font-semibold">{group.healthyCount}<span className="text-sm font-normal text-ink-3"> / {group.accountCount} 正常</span></div></Card>)}</div>
      {creating && <GroupForm onClose={() => setCreating(false)} onSaved={() => { setCreating(false); cn.reload(); global.reload(); }} />}
    </>
  );
}

function strategyLabel(value?: string) {
  return { round_robin: "轮询", most_credits: "积分最多", recent_active: "最近活跃", least_used: "最少使用" }[value ?? ""] ?? "轮询";
}

function GroupForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ region: "cn" as Region, name: "", description: "", strategy: "round_robin" });
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4">
      <form onSubmit={(event) => { event.preventDefault(); void run("创建分组", () => client().createGroup(form), "分组已创建").then((result) => result && onSaved()); }} className="w-full max-w-md space-y-3 rounded-lg bg-surface p-5 shadow-sheet">
        <div className="flex items-center justify-between"><h2 className="font-semibold">新建分组</h2><button type="button" onClick={onClose}><X size={16} /></button></div>
        <Field label="区域"><select value={form.region} onChange={(event) => setForm({ ...form, region: event.target.value as Region })} className={inputClass}><option value="cn">国内版</option><option value="global">国际版</option></select></Field>
        <Field label="名称"><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={inputClass} /></Field>
        <Field label="路由策略"><select value={form.strategy} onChange={(event) => setForm({ ...form, strategy: event.target.value })} className={inputClass}><option value="round_robin">轮询</option><option value="most_credits">积分最多</option><option value="least_used">最少使用</option><option value="recent_active">最近活跃</option></select></Field>
        <Field label="描述"><input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} className={inputClass} /></Field>
        <button className="h-9 w-full rounded-md bg-accent text-xs font-medium text-white">保存</button>
      </form>
    </div>
  );
}

function Checkin() {
  const summary = useLive(async () => (await client().checkinSummary()).data, []);
  const records = useLive(async () => as<CheckinRecord[]>((await client().checkinRecords()).data.items), []);
  const accounts = useLive(async () => {
    const [cn, global] = await Promise.all([client().accounts("cn", { limit: 200 }), client().accounts("global", { limit: 200 })]);
    return as<AccountRow[]>([...cn.data.items, ...global.data.items]);
  }, []);
  const names = useMemo(() => new Map((accounts.data ?? []).map((row) => [row.id, row.name])), [accounts.data]);
  const [job, setJob] = useState<Record<string, unknown> | null>(null);

  const checkAll = async () => {
    const created = await run("创建签到任务", () => client().createCheckinJob({ scope: "all" }), "任务已创建");
    const jobs = as<{ jobs?: { id: string }[] }>(created && (created as { data: unknown }).data)?.jobs ?? [];
    if (jobs.length === 0) return;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const current = await client().checkinJob(jobs[0].id);
      setJob(current.data);
      if (current.data.status === "completed") break;
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    records.reload();
    summary.reload();
  };

  return (
    <>
      <Header eyebrow="Check-in & Credits" title="签到管理" description="签到成功与积分到账是两件事。到账只在余额同步差额与奖励一致时标为已确认。" action={<button onClick={() => void checkAll()} className="flex h-9 items-center gap-2 rounded-md bg-accent px-3.5 text-xs font-medium text-white"><CalendarCheck size={15} />签到全部待签到</button>} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="账号总数" value={formatNumber(summary.data?.total)} />
        <Metric label="进行中" value={formatNumber(summary.data?.pending)} tone="orange" />
        <Metric label="签到成功" value={formatNumber(summary.data?.success)} tone="green" />
        <Metric label="签到失败" value={formatNumber(summary.data?.failed)} tone="orange" />
        <Metric label="待确认到账" value={formatNumber(summary.data?.awaitingArrival)} />
      </div>
      {job && <Card className="mt-4 p-4 text-xs text-ink-2">任务 {String(job.id)} · {String(job.status)} · 成功 {String(job.success ?? 0)} · 失败 {String(job.failed ?? 0)} · 跳过 {String(job.skipped ?? 0)}</Card>}
      <Card className="mt-5">
        <div className="border-b border-line p-5"><h2 className="t-title">签到记录</h2><p className="mt-1 text-xs text-ink-2">失败可以重试；进行中的记录不会被重复提交。</p></div>
        <Notice state={{ ...records, empty: (records.data ?? []).length === 0 }} />
        {(records.data ?? []).length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-xs"><thead><tr className="border-b border-line text-ink-3"><th className="px-5 py-3 font-medium">账号</th><th className="px-3 py-3 font-medium">区域</th><th className="px-3 py-3 font-medium">状态</th><th className="px-3 py-3 font-medium">积分到账</th><th className="px-3 py-3 font-medium">时间</th><th className="px-5 py-3 font-medium">操作</th></tr></thead>
          <tbody>{records.data?.map((row) => <tr key={row.id} className="border-b border-line last:border-0"><td className="px-5 py-4 font-medium">{names.get(row.accountId) ?? row.accountId}</td><td className="px-3 py-4"><RegionBadge region={row.region} /></td><td className="px-3 py-4">{row.result === "success" ? <span className="text-success">已签到</span> : <span className="text-danger">失败 · {row.failReason}</span>}</td><td className="px-3 py-4">{arrivalLabel(row.arrival)}</td><td className="px-3 py-4 text-ink-2">{formatRelative(row.at)}</td><td className="px-5 py-4"><button onClick={() => void run("重试签到", () => client().checkinAccount(row.accountId), "已执行").then(() => records.reload())} className="text-accent">重试</button></td></tr>)}</tbody>
        </table></div>}
      </Card>
    </>
  );
}

function arrivalLabel(value: CheckinRecord["arrival"]) {
  if (value === "credited") return "已确认到账";
  if (value === "pending") return "待确认";
  if (value === "unknown") return "无法确认";
  return "—";
}

function Credits() {
  const [region, setRegion] = useState<"" | Region>("");
  const [type, setType] = useState("");
  const summary = useLive(async () => as<CreditsSummary & { unconfirmedAccounts?: number }>((await client().creditSummary(region || undefined)).data), [region]);
  const entries = useLive(async () => as<LedgerEntry[]>((await client().credits(region || undefined, type || undefined)).data.items), [region, type]);
  const accounts = useLive(async () => as<AccountRow[]>([...(await client().accounts("cn", { limit: 200 })).data.items, ...(await client().accounts("global", { limit: 200 })).data.items]), []);
  const names = new Map((accounts.data ?? []).map((row) => [row.id, row.name]));

  const download = async () => {
    const blob = await run("导出中", () => client().exportCredits(region || undefined), "已导出");
    if (!blob) return;
    const url = URL.createObjectURL(blob as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "credits.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <Header eyebrow="Check-in & Credits" title="积分记录" description="只展示已确认的流水。签到成功本身不会产生流水。" action={<button onClick={() => void download()} className="h-9 rounded-md bg-fill-2 px-3.5 text-xs">导出 CSV</button>} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="已确认总积分" value={formatNumber(summary.data?.totalBalance)} />
        <Metric label="今日获得" value={formatNumber(summary.data?.earnedToday)} tone="green" />
        <Metric label="今日消耗" value={formatNumber(summary.data?.consumedToday)} tone="orange" />
        <Metric label="累计获得" value={formatNumber(summary.data?.earnedAllTime)} />
        <Metric label="累计消耗" value={formatNumber(summary.data?.consumedAllTime)} />
      </div>
      <Card className="mt-5">
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          {[["", "全部"], ["checkin", "签到获取"], ["api_usage", "API 消耗"], ["adjustment", "调整"]].map(([value, label]) => <button key={value} onClick={() => setType(value)} className={`rounded-md px-3 py-1.5 text-xs ${type === value ? "bg-ink text-bg" : "bg-fill-2 text-ink-2"}`}>{label}</button>)}
          <select value={region} onChange={(event) => setRegion(event.target.value as "" | Region)} className="ml-auto h-8 rounded-md bg-fill-2 px-2 text-xs"><option value="">全部区域</option><option value="cn">国内版</option><option value="global">国际版</option></select>
        </div>
        <Notice state={{ ...entries, empty: (entries.data ?? []).length === 0 }} />
        {(entries.data ?? []).length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left text-xs"><thead><tr className="border-b border-line text-ink-3"><th className="px-5 py-3 font-medium">时间</th><th className="px-3 py-3 font-medium">账号</th><th className="px-3 py-3 font-medium">类型</th><th className="px-3 py-3 font-medium">变动</th><th className="px-3 py-3 font-medium">变动前</th><th className="px-3 py-3 font-medium">变动后</th><th className="px-5 py-3 font-medium">备注</th></tr></thead>
          <tbody>{entries.data?.map((row) => <tr key={row.id} className="border-b border-line last:border-0"><td className="px-5 py-4 text-ink-2">{formatRelative(row.at)}</td><td className="px-3 py-4 font-medium">{names.get(row.accountId) ?? row.accountId}</td><td className="px-3 py-4">{row.type === "checkin" ? "签到获取" : row.type === "api_usage" ? "API 消耗" : "调整"}</td><td className={`px-3 py-4 font-medium tnum ${row.delta > 0 ? "text-success" : "text-danger"}`}>{row.delta > 0 ? "+" : ""}{row.delta}</td><td className="px-3 py-4 tnum">{formatNumber(row.balanceBefore)}</td><td className="px-3 py-4 tnum">{formatNumber(row.balanceAfter)}</td><td className="px-5 py-4 text-ink-2">{row.note}</td></tr>)}</tbody>
        </table></div>}
      </Card>
    </>
  );
}

function Gateway() {
  const state = useLive(async () => as<GatewayStatus>((await client().gatewayStatus()).data), []);
  const logs = useLive(async () => as<RuntimeLogLine[]>((await client().runtimeLogs()).data.items), []);
  const [showLogs, setShowLogs] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const data = state.data;
  const act = (action: "start" | "stop" | "restart", label: string) => void run(label, () => client().gatewayAction(action), "已更新").then(() => state.reload());
  return (
    <>
      <Header eyebrow="API Gateway" title="API 服务" description="网关与管理端共用同一进程。停止只拒绝新的转发，不会杀掉进程。" action={<div className="flex gap-2"><button onClick={() => setShowLogs(true)} className="h-9 rounded-md bg-fill-2 px-3 text-xs">查看运行日志</button>{data?.state === "running" ? <button onClick={() => setConfirmStop(true)} className="h-9 rounded-md bg-fill-2 px-3 text-xs">停止服务</button> : <button onClick={() => act("start", "启动中")} className="h-9 rounded-md bg-ink px-3.5 text-xs font-medium text-bg">启动服务</button>}<button onClick={() => act("restart", "重启中")} className="h-9 rounded-md bg-ink px-3.5 text-xs font-medium text-bg">重启服务</button></div>} />
      <Notice state={state} />
      {data && <Card className="mb-4 p-5"><div className="flex flex-wrap items-center justify-between gap-4"><div className="flex items-center gap-3"><div className={`grid size-11 place-items-center rounded-full ${data.state === "running" ? "bg-success-soft text-success" : "bg-neutral-soft text-ink-2"}`}><Server size={22} /></div><div><div className="text-base font-semibold">{data.state === "running" ? "网关运行中" : "网关已停止"}</div><div className="mt-1 text-xs text-ink-2">监听 {data.host}:{data.port}</div></div></div><div className="grid grid-cols-3 gap-6 text-right text-xs"><div><div className="text-ink-3">累计请求</div><div className="mt-1 text-lg font-semibold tnum">{formatNumber(data.totalRequests)}</div></div><div><div className="text-ink-3">成功率</div><div className="mt-1 text-lg font-semibold tnum">{data.successRate === null ? "未知" : `${data.successRate}%`}</div></div><div><div className="text-ink-3">平均响应</div><div className="mt-1 text-lg font-semibold tnum">{data.avgLatencyMs === null ? "未知" : `${data.avgLatencyMs} ms`}</div></div></div></div></Card>}
      <div className="grid gap-4 lg:grid-cols-2">{data?.protocols.map((item) => <Card key={item.endpoint} className="p-5"><div className="flex items-center justify-between"><div><div className="font-medium">{item.name}</div><div className="mt-1 font-mono text-xs text-accent">{item.method} {item.endpoint}</div></div><button onClick={() => void navigator.clipboard.writeText(item.endpoint).then(() => toast.success("已复制"))} className="rounded-md p-2 text-ink-3 hover:bg-fill" title="复制 Endpoint"><Copy size={15} /></button></div><div className="mt-5 flex gap-8 text-xs"><div><span className="text-ink-3">请求数量</span><div className="mt-1 font-semibold tnum">{formatNumber(item.requests)}</div></div><div><span className="text-ink-3">状态</span><div className="mt-1">{item.enabled ? "已启用" : "已停用"}</div></div><div><span className="text-ink-3">最近调用</span><div className="mt-1">{formatRelative(item.lastCalledAt)}</div></div></div></Card>)}</div>
      {showLogs && <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4"><Card className="max-h-[70vh] w-full max-w-lg overflow-auto p-5"><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">运行日志</h2><button onClick={() => setShowLogs(false)}><X size={16} /></button></div>{(logs.data ?? []).length === 0 && <div className="text-xs text-ink-3">暂无日志</div>}{(logs.data ?? []).map((line) => <div key={line.id} className="border-b border-line py-2 text-xs"><span className="text-ink-3">{formatRelative(line.at)} · {line.level}</span><div>{line.message}</div></div>)}</Card></div>}
      {confirmStop && <Confirm title="停止网关" detail="停止后所有转发请求会返回 503，直到再次启动。" onClose={() => setConfirmStop(false)} onConfirm={() => { setConfirmStop(false); act("stop", "停止中"); }} />}
    </>
  );
}

function Keys() {
  const state = useLive(async () => as<ApiKey[]>((await client().keys()).data.items), []);
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [removing, setRemoving] = useState<ApiKey | null>(null);
  return (
    <>
      <Header eyebrow="API Gateway" title="API Keys" description="完整密钥只在创建成功时显示一次，之后只保留掩码。" action={<button onClick={() => setCreating(true)} className="h-9 rounded-md bg-accent px-3.5 text-xs font-medium text-white">+ 新建</button>} />
      <Notice state={{ ...state, empty: (state.data ?? []).length === 0 }} />
      <Card className="divide-y divide-line">{(state.data ?? []).map((key) => <div key={key.id} className="flex items-center gap-4 p-5"><div className="grid size-9 place-items-center rounded-lg bg-fill-2 text-ink-2"><KeyRound size={16} /></div><div className="flex-1"><div className="text-sm font-medium">{key.name}</div><div className="mt-1 font-mono text-xs text-ink-3">{key.masked} · {key.enabled ? "已启用" : "已停用"} · {formatNumber(key.requestCount)} 次调用</div></div><button onClick={() => void run(key.enabled ? "停用中" : "启用中", () => client().updateKey(key.id, { enabled: !key.enabled }), "已更新").then(() => state.reload())} className="text-xs text-ink-2">{key.enabled ? "停用" : "启用"}</button><button onClick={() => setRemoving(key)} className="text-xs text-danger">删除</button></div>)}</Card>
      {creating && <KeyForm onClose={() => setCreating(false)} onCreated={(value) => { setCreating(false); setSecret(value); state.reload(); }} />}
      {secret && <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4"><Card className="w-full max-w-md p-5"><h2 className="font-semibold">密钥已创建</h2><p className="mt-2 text-xs text-ink-2">关闭后无法再次查看完整值。</p><div className="mt-3 break-all rounded-md bg-fill-2 p-3 font-mono text-xs">{secret}</div><div className="mt-4 flex justify-end gap-2"><button onClick={() => void navigator.clipboard.writeText(secret).then(() => toast.success("已复制"))} className="h-8 rounded-md bg-fill-2 px-3 text-xs">复制</button><button onClick={() => setSecret(null)} className="h-8 rounded-md bg-accent px-3 text-xs text-white">我已保存</button></div></Card></div>}
      {removing && <Confirm title={`删除 ${removing.name}`} detail="有请求记录的密钥无法删除，请改为停用。" onClose={() => setRemoving(null)} onConfirm={() => { const key = removing; setRemoving(null); void run("删除中", () => client().deleteKey(key.id), "已删除").then(() => state.reload()); }} />}
    </>
  );
}

function KeyForm({ onClose, onCreated }: { onClose: () => void; onCreated: (secret: string) => void }) {
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4">
      <form onSubmit={(event) => { event.preventDefault(); void run("创建密钥", () => client().createKey({ name, note }), "已创建").then((result) => result && onCreated((result as { data: { secret: string } }).data.secret)); }} className="w-full max-w-sm space-y-3 rounded-lg bg-surface p-5 shadow-sheet">
        <div className="flex items-center justify-between"><h2 className="font-semibold">新建 API Key</h2><button type="button" onClick={onClose}><X size={16} /></button></div>
        <Field label="名称"><input required value={name} onChange={(event) => setName(event.target.value)} className={inputClass} /></Field>
        <Field label="备注"><input value={note} onChange={(event) => setNote(event.target.value)} className={inputClass} /></Field>
        <button className="h-9 w-full rounded-md bg-accent text-xs font-medium text-white">创建</button>
      </form>
    </div>
  );
}

function Models() {
  const [region, setRegion] = useState<"" | Region>("");
  const state = useLive(async () => as<ModelInfo[]>((await client().models(region || undefined)).data.items), [region]);
  const caps = useLive(async () => as<Capabilities>((await client().capabilities()).data), []);
  return (
    <>
      <Header eyebrow="API Gateway" title="模型管理" description="只显示上游发现或实际调用过的模型，没有内置目录。" action={<button disabled={!caps.data?.modelDiscovery} onClick={() => void run("发现模型", () => client().discoverModels(region || "cn"), "发现完成").then(() => state.reload())} className="h-9 rounded-md bg-accent px-3.5 text-xs font-medium text-white disabled:opacity-50">{caps.data?.modelDiscovery ? "发现模型" : "未配置发现地址"}</button>} />
      <div className="mb-4"><select value={region} onChange={(event) => setRegion(event.target.value as "" | Region)} className="h-9 rounded-md bg-fill-2 px-3 text-xs"><option value="">全部区域</option><option value="cn">国内版</option><option value="global">国际版</option></select></div>
      <Notice state={{ ...state, empty: (state.data ?? []).length === 0 }} />
      <Card className="divide-y divide-line">{(state.data ?? []).map((model) => <div key={model.id} className="flex items-center gap-4 p-5"><div className="grid size-9 place-items-center rounded-lg bg-fill-2 text-ink-2"><Boxes size={16} /></div><div className="flex-1"><div className="text-sm font-medium">{model.displayName}</div><div className="mt-1 text-xs text-ink-3">{model.regions.join(" / ")} · {model.enabled ? "已启用" : "已停用"} · 24 小时 {model.requests24h} 次</div></div><button onClick={() => void run("更新中", () => client().setModelEnabled(model.id, !model.enabled), "已更新").then(() => state.reload())} className="text-xs text-accent">{model.enabled ? "停用" : "启用"}</button></div>)}</Card>
    </>
  );
}

function Logs() {
  const [search, setSearch] = useState("");
  const [protocol, setProtocol] = useState("");
  const [status, setStatus] = useState("");
  const state = useLive(async () => as<RequestLog[]>((await client().logs({ search, protocol, status, limit: 50 })).data.items), [search, protocol, status]);
  const accounts = useLive(async () => as<AccountRow[]>([...(await client().accounts("cn", { limit: 200 })).data.items, ...(await client().accounts("global", { limit: 200 })).data.items]), []);
  const names = new Map((accounts.data ?? []).map((row) => [row.id, row.name]));
  return (
    <>
      <Header eyebrow="API Gateway" title="请求日志" description="敏感请求头已在服务端脱敏。" action={<button onClick={state.reload} className="h-9 rounded-md bg-fill-2 px-3 text-xs">刷新</button>} />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          <div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-2.5 text-ink-3" size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索请求 ID 或模型" className="h-9 w-full rounded-md bg-fill-2 pl-9 text-xs outline-none focus:ring-2 focus:ring-accent" /></div>
          <select value={protocol} onChange={(event) => setProtocol(event.target.value)} className="h-9 rounded-md bg-fill-2 px-3 text-xs"><option value="">全部协议</option><option value="anthropic">Anthropic</option><option value="openai_chat">OpenAI Chat</option><option value="openai_responses">OpenAI Responses</option></select>
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="h-9 rounded-md bg-fill-2 px-3 text-xs"><option value="">全部状态</option><option value="success">成功</option><option value="error">失败</option></select>
        </div>
        <Notice state={{ ...state, empty: (state.data ?? []).length === 0 }} />
        {(state.data ?? []).length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left text-xs"><thead><tr className="border-b border-line text-ink-3"><th className="px-5 py-3 font-medium">时间</th><th className="px-3 py-3 font-medium">请求 ID</th><th className="px-3 py-3 font-medium">协议 / 模型</th><th className="px-3 py-3 font-medium">上游账号</th><th className="px-3 py-3 font-medium">状态</th><th className="px-3 py-3 font-medium">消耗</th><th className="px-5 py-3 font-medium">响应时间</th></tr></thead>
          <tbody>{state.data?.map((row) => <tr key={row.id} className="border-b border-line last:border-0"><td className="px-5 py-4 text-ink-2">{formatRelative(row.at)}</td><td className="px-3 py-4 font-mono text-[11px]">{row.id}</td><td className="px-3 py-4"><div>{row.protocol}</div><div className="mt-1 text-[11px] text-ink-3">{row.resolvedModel}</div></td><td className="px-3 py-4">{row.accountId ? names.get(row.accountId) ?? row.accountId : "—"}</td><td className="px-3 py-4"><span className={row.status === "success" ? "text-success" : "text-danger"}>{row.httpStatus} · {row.status === "success" ? "成功" : "失败"}</span></td><td className="px-3 py-4 tnum">{row.credits ?? "未知"}</td><td className="px-5 py-4 tnum">{row.latencyMs} ms</td></tr>)}</tbody>
        </table></div>}
      </Card>
    </>
  );
}

function SettingsView() {
  const state = useLive(async () => as<SettingsModel>((await client().settings()).data), []);
  const [override, setOverride] = useState<{ base: SettingsModel; value: SettingsModel } | null>(null);
  const draft = override && override.base === state.data ? override.value : state.data;
  const setDraft = (value: SettingsModel) => {
    if (state.data) setOverride({ base: state.data, value });
  };
  if (!draft) return <Notice state={state} />;
  const save = () => void run("保存中", () => client().saveSettings(draft), "已保存").then(() => state.reload());
  return (
    <>
      <Header eyebrow="System" title="系统设置" description="保存后由后端校验。未核实的能力不会被打开。" action={<button onClick={save} className="h-9 rounded-md bg-accent px-3.5 text-xs font-medium text-white">保存更改</button>} />
      <div className="space-y-4">
        <Card className="p-5"><h2 className="t-title">基础设置</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><Field label="系统名称"><input value={draft.general.systemName} onChange={(event) => setDraft({ ...draft, general: { ...draft.general, systemName: event.target.value } })} className={inputClass} /></Field><Field label="时区"><input value={draft.general.timezone} onChange={(event) => setDraft({ ...draft, general: { ...draft.general, timezone: event.target.value } })} className={inputClass} /></Field></div></Card>
        <Card className="p-5"><div className="flex items-center justify-between"><div><h2 className="t-title">签到设置</h2><p className="mt-1 text-xs text-ink-2">自动签到由独立 worker 按租约执行，失败不会被重复回放。</p></div><button type="button" onClick={() => setDraft({ ...draft, checkin: { ...draft.checkin, auto: !draft.checkin.auto } })} className={`relative h-6 w-11 rounded-full ${draft.checkin.auto ? "bg-accent" : "bg-fill"}`} aria-pressed={draft.checkin.auto} aria-label="自动签到"><span className={`absolute top-1 size-4 rounded-full bg-white ${draft.checkin.auto ? "right-1" : "left-1"}`} /></button></div><div className="mt-5 grid gap-4 sm:grid-cols-2"><Field label="每日执行时间"><input type="time" value={draft.checkin.time} onChange={(event) => setDraft({ ...draft, checkin: { ...draft.checkin, time: event.target.value } })} className="h-9 rounded-md bg-fill-2 px-3" /></Field><Field label="失败重试次数"><input type="number" min={0} max={5} value={draft.checkin.maxRetries} onChange={(event) => setDraft({ ...draft, checkin: { ...draft.checkin, maxRetries: Number.parseInt(event.target.value, 10) || 0 } })} className="h-9 rounded-md bg-fill-2 px-3" /></Field></div><div className="mt-4 flex gap-4 text-xs">{(["cn", "global"] as Region[]).map((region) => <label key={region} className="flex items-center gap-2"><input type="checkbox" checked={draft.checkin.regions.includes(region)} onChange={() => setDraft({ ...draft, checkin: { ...draft.checkin, regions: draft.checkin.regions.includes(region) ? draft.checkin.regions.filter((item) => item !== region) : [...draft.checkin.regions, region] } })} />{region === "cn" ? "国内版" : "国际版"}</label>)}</div>{draft.checkin.auto && draft.checkin.regions.length === 0 && <p className="mt-3 text-xs text-warning">开启自动签到前至少选择一个区域，否则无法保存。</p>}</Card>
        <Card className="p-5"><h2 className="t-title">API 设置</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><Field label="超时（秒）"><input type="number" value={draft.api.timeoutSec} onChange={(event) => setDraft({ ...draft, api: { ...draft.api, timeoutSec: Number.parseInt(event.target.value, 10) || 0 } })} className={inputClass} /></Field><Field label="默认模型"><input value={draft.api.defaultModel} onChange={(event) => setDraft({ ...draft, api: { ...draft.api, defaultModel: event.target.value } })} placeholder="留空则不改写模型名" className={inputClass} /></Field></div></Card>
      </div>
    </>
  );
}

function Status() {
  const state = useLive(async () => (await client().runtime()).data, []);
  const data = state.data;
  const rows = data ? [
    { name: "数据库", detail: String(data.database), tone: data.database === "operational" ? "success" : "warning", icon: <HeartPulse size={17} /> },
    { name: "国内版上游", detail: "agent.minimax.cn · 未主动探测", tone: "neutral", icon: <Globe size={17} /> },
    { name: "国际版上游", detail: `agent.minimax.io · 过期账号 ${String(data.expiredAccounts)} 个`, tone: Number(data.expiredAccounts) > 0 ? "warning" : "success", icon: <Globe size={17} /> },
    { name: "签到队列", detail: `排队任务 ${String(data.queuedJobs)} 个`, tone: "success", icon: <CalendarCheck size={17} /> },
  ] : [];
  return (
    <>
      <Header eyebrow="System" title="运行状态" description="只展示已核实的状态。上游连通性不会被假装成已检测。" action={<button onClick={state.reload} className="flex h-9 items-center gap-2 rounded-md bg-fill-2 px-3 text-xs"><Activity size={14} />重新检查</button>} />
      <Notice state={state} />
      {data && <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]"><Card className="divide-y divide-line"><div className="p-5"><h2 className="t-title">组件健康</h2><p className="mt-1 text-xs text-ink-2">数据来源：{String(data.dataSource)}</p></div>{rows.map((item) => <div key={item.name} className="flex items-center gap-3 p-4"><div className="grid size-9 place-items-center rounded-lg bg-fill-2 text-ink-2">{item.icon}</div><div className="flex-1"><div className="text-sm font-medium">{item.name}</div><div className="mt-1 text-xs text-ink-2">{item.detail}</div></div><div className={`text-xs ${item.tone === "warning" ? "text-warning" : item.tone === "success" ? "text-success" : "text-ink-3"}`}>{item.tone === "warning" ? "需关注" : item.tone === "success" ? "正常" : "未知"}</div></div>)}</Card><Card className="p-5"><div className="text-sm font-semibold">版本 {String(data.version)}</div><div className="mt-2 text-xs text-ink-2">Python {String(data.pythonVersion)}</div><div className="mt-1 text-xs text-ink-3">{String(data.platform)}</div></Card></div>}
    </>
  );
}
