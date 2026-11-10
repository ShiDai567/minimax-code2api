# MiniMax Code2API 前端

Next.js 16 App Router、React 19、TypeScript 与 Tailwind CSS v4 管理界面。页面通过 `src/lib/api.ts` 读取 Django 后端，不再使用 mock 数据。

## 本地开发

```bash
npm install
npm run dev
```

默认打开 `http://localhost:3000`，请求 `http://127.0.0.1:8045`。用 `NEXT_PUBLIC_API_BASE_URL` 修改后端地址。这个变量会进入浏览器包，只能放公开地址，不能放管理令牌或其他密钥。

```bash
npm run lint
npx tsc --noEmit
npm run build
```

## 登录

打开页面后输入 `CONSOLE_PASSWORD`。登录后的签名令牌只存在浏览器的 `localStorage`，不会写进代码。退出登录只清除本地令牌。

完整的启动方式和后端接口见仓库根目录 [README](../README.md)。
