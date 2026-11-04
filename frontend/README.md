# MiniMax Code2API 前端

Next.js 16 App Router、React 19、TypeScript 与 Tailwind CSS v4 管理界面。当前页面使用 `src/lib/mock.ts` 中的 mock 数据；`src/lib/api.ts` 是后端 client 的初始封装，但尚未接入全部页面。因此页面内容不能视为后端实时数据。

## 本地开发

```bash
npm install
npm run dev
```

默认打开 `http://localhost:3000`。代码检查：

```bash
npm run lint
npx tsc --noEmit
npm run build
```

## 后端 API client

`NEXT_PUBLIC_API_BASE_URL` 可设置 `src/lib/api.ts` 使用的后端基础地址，默认 `http://127.0.0.1:8045`。本变量会暴露给浏览器，只能放公开服务地址等非秘密配置，绝不能放管理 Token 或其他密钥。

启用跨域联调前，需要由同源代理或后端部署层提供经过限制的 CORS 配置。不要为了开发方便把管理端 token 写入客户端 bundle。完整项目启动和后端接口状态见仓库根目录 [README](../README.md) 与 [API 文档](../docs/api.md)。
