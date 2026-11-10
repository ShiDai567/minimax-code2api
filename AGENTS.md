# AGENTS.md

## 仓库现状（2026-11-10 核实）

- 前端代码全部放在 `frontend/` 下，当前实现是 Next.js 16 App Router + React 19 + TypeScript + Tailwind CSS v4 + Lucide React；依赖和脚本以 `frontend/package.json` 为准。
- 后端在 `backend/`，Django 5 + Django REST framework + MySQL 8.0（开发环境可用 SQLite）。页面经 `frontend/src/lib/api.ts` 读取 `/api/v1/`，不再使用 mock 数据。
- 未核实的上游能力不要编造成可用：余额同步、模型发现、token 刷新在缺少已核实配置时必须返回明确错误。

## 开发命令

在 `frontend/` 目录执行：

```bash
npm install
npm run dev       # 开发服务器，默认 http://localhost:3000
npm run lint
npx tsc --noEmit
npm run build
```

建议验证顺序：`npm run lint` → `npx tsc --noEmit` → `npm run build`。Next 配置启用了 `cacheComponents` 和 `partialPrefetching`；使用 `usePathname`、`useSearchParams` 等客户端路由 hook 时必须放在 `Suspense` 边界内。

## 产品范围

MiniMax Code2API：用于统一管理 MiniMax Code 国内版和国际版账号的 Web 管理后台，覆盖自动签到、积分监控，以及 API 网关（Anthropic / OpenAI Chat / OpenAI Responses 协议转换）。

导航结构（与路由一一对应，每个页面都要有完整 UI，不允许占位页）：
- Overview：仪表盘
- Account Management：国内版账号、国际版账号、账号分组
- Check-in & Credits：签到管理、积分记录
- API Gateway：API 服务、API Keys、模型管理、请求日志
- System：系统设置、运行状态

## 设计规则

- 视觉以 `apple-design` skill 为最高优先级。写 UI 之前先用 skill 工具加载它。需要更深的打磨时可加载 `emil-design-eng` / `ui-animation`。
- Apple 风格负责视觉品质，信息密度和效率不能为它让步。不要做成 Ant Design Pro / Element Admin 那种模板化后台。避免花哨的渐变、彩色统计卡片、密集的边框和分割线、装饰性图表、不统一的圆角。
- 状态不能只靠颜色区分，必须同时带文字或图标（签到状态：成功 / 等待中 / 失败 / 未执行）。
- 支持深色和浅色主题，遵循 `prefers-reduced-motion`，适配桌面到手机的布局（小屏下表格可横向滚动）。
- 参考项目只用来理解业务，不要照搬它们的 UI。

## 领域约束（容易出错）

- 国内版和国际版是相互独立的区域，账号、凭证、筛选和统计都分开管理，只有仪表盘可以汇总。不要把两个区域合并到一个账号表里，也不要假设它们的 API 一致。
  - 官方 CLI：`mcode login`（中国大陆）和 `mcode login --region global`。参考网关里对应 `region: cn` → `agent.minimax.cn`，`region: io` → `agent.minimax.io`。
- 参考网关（github.com/syxscott/minimax-code2api，零依赖 Node ≥18.17，默认 `127.0.0.1:8045`）只暴露以下接口：`POST /v1/messages`、`/v1/messages/count_tokens`、`/v1/chat/completions`、`/v1/responses`、`GET /v1/models`、`GET /health`。它的 access token 是通过本地命名管道从 MiniMax Code 桌面端租用的，`apiKeys` 为空时不做鉴权。
- 已核实的参考项目都没有签到、积分、多账号相关的接口，这些都是新设计的后端接口：
  - 不要编造接口，也不要把签到成功等同于积分已到账。
  - 不要硬编码模型 ID、能力或价格，模型列表从 `/v1/models` 或 adapter 动态获取。

## 数据层

- 所有数据访问都经过 `frontend/src/lib/api.ts`，页面不直接拼请求。接入新接口时先改这里，再改页面。
- 响应带 `source`。未核实或未同步的数值用 `null` 表示，界面显示“未知”，不要用 0 代替。
- 账目必须平衡：`balance_after = balance_before + delta`。签到成功本身不产生流水，只有余额同步确认差额后才入账。
- 凭证默认脱敏：Token 不在列表里展示，API Key 的完整值只在创建成功时显示一次，请求头里的敏感字段在日志详情中脱敏。

## 交互规则

- 有业务意义的操作要完整呈现：操作前状态 → 加载中 → 成功或失败的 toast，危险操作（删除、停止或重启服务、批量删除）需要二次确认。
- 批量操作（例如批量签到）要显示进度以及成功和失败的数量，不能只弹一个笼统的成功提示。
- 列表都要支持搜索、筛选、排序、分页、多选，并处理空状态、加载状态和错误状态。

## 完成标准

- 声称完成之前，typecheck 和 build 必须通过，并且实际运行 dev server，确认每个导航页都能打开、没有控制台报错，深色和浅色主题都要检查。
