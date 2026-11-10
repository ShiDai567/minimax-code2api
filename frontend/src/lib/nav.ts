export const navGroups = [
  { label: "概览", items: [{ label: "仪表盘", href: "/", icon: "layout" }] },
  { label: "账号管理", items: [{ label: "国内版账号", href: "/accounts/cn", icon: "users" }, { label: "国际版账号", href: "/accounts/global", icon: "globe" }, { label: "账号分组", href: "/accounts/groups", icon: "layers" }] },
  { label: "签到与积分", items: [{ label: "签到管理", href: "/checkin", icon: "calendar" }, { label: "积分记录", href: "/credits", icon: "coins" }] },
  { label: "API 网关", items: [{ label: "API 服务", href: "/gateway", icon: "server" }, { label: "API Keys", href: "/gateway/keys", icon: "key" }, { label: "模型管理", href: "/gateway/models", icon: "boxes" }, { label: "请求日志", href: "/gateway/logs", icon: "logs" }] },
  { label: "系统", items: [{ label: "系统设置", href: "/settings", icon: "settings" }, { label: "运行状态", href: "/status", icon: "activity" }] },
];
