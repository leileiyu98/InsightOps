# M1.4 React Demo UI

## 目标与范围

M1.4 为既有 M1.3 Text2SQL API 提供可截图、可录屏的单页 Analytics Copilot：业务问题 → SQL 或澄清 →
deterministic evaluation 状态 → 结果表 → 后端业务摘要。范围仅包括展示层与 production 静态托管，不改变
`POST /v1/query`、`GET /health`、数据库、provider、benchmark 或 evaluation 合同。

## 前端结构

- `src/api/query.ts`：相对路径 Fetch、30 秒 timeout、取消、HTTP error 合同和轻量 runtime guard。
- `src/types/query.ts`：与 Pydantic public contract 对齐的请求、成功、错误、action 和 status 类型。
- `src/components/`：composer、reviewed examples、request status、SQL、结果、summary、clarification 和错误状态。
- `src/App.tsx`：局部 React 状态与 AbortController 生命周期；不引入 router 或全局状态。
- `src/styles/index.css`：桌面优先、375px 可用、键盘 focus 和 reduced-motion 的原生 CSS。

前端不接收 provider、model、key 或数据库配置，不使用 storage、动态 HTML、外部字体/CDN、SQL 编辑或执行能力。
空 case ID 不进入请求 body；过期请求被 sequence guard 阻止覆盖新状态。

## 开发与 production 集成

Vite development server 将 `/v1` 和 `/health` 代理到 FastAPI。production build 写入被忽略的
`frontend/dist/`，现有应用工厂条件式提供 `/` 与 `/assets/*`。build 缺失不会阻止 FastAPI 导入，也不会提前
初始化 query service、OpenAI client 或数据库 engine。

## 测试与验收

Vitest/Testing Library 覆盖初始页面、examples、空输入、执行、澄清、unscored、provider error、loading、clear、
copy、NULL、malformed response 与 health online/offline。pytest 覆盖 build presence/absence、static assets、API
保活和源码安全回归。CI 固定 Node 22.12，通过 `package-lock.json` 运行 lint、typecheck、tests 和 production
build，并继续运行全部 Python、migration 与 health checks。

## 已知限制

- 单页无路由、历史、登录、多轮会话、流式输出、图表、分页或导出。
- 健康状态是页面加载时的一次 liveness 检查，不是持续监控或数据库 readiness。
- fake provider 仍只支持三个固定 benchmark case 和一个固定自由查询；UI 不扩展其语言理解范围。
- `frontend/dist/` 是本地产物，不提交到 Git；部署流程必须先执行 production build。
