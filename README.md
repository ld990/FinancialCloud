# 金融K8s容器安全基线与可视化平台（毕业设计）

面向金融行业的 Kubernetes 可观测与安全治理平台原型，提供资源总览、合规审计、事件订阅、风险修复建议、周报预览等能力，支持基础账号登录与最小权限建议指引，便于导师与评审从功能与工程实现两个维度进行验收与评估。

## 功能特性
- **仪表盘总览**：集群核心指标与关键告警的可视化展示（`Dashboard`）。
- **合规审计**：对资源配额、特权、HostPath 等高风险项进行扫描与列表化呈现，并给出修复建议（`Audit`）。
- **事件订阅**：通过 SSE 实时获取 K8s Events，前端按时间倒序展示（`Events`）。
- **资源视图**：CPU/内存等使用情况聚合展示（`Resources`）。
- **风险修复**：根据审计项生成可执行的修复建议包（`FixAssistant`）。
- **报表预览**：生成周报 HTML 预览，支持导出（`ReportExport`）。
- **账号管理**：登录、退出与当前账号信息查看，结合最小权限原则给出建议（`Account`）。

## 技术架构
- **前端**：Vue 3 + Vite + Vue Router + Element Plus + ECharts，SSE 订阅事件流。
- **后端**：FastAPI + Uvicorn，封装 Kubernetes Python SDK，提供鉴权、审计、资源与事件接口。
- **通信协议**：REST API + Server-Sent Events（SSE）。

目录结构（关键部分）：
```
FinancialCloud/
├─ frontend/               # Web 前端（Vue 3 + Vite）
│  ├─ src/
│  │  ├─ api/              # 前端 API 封装
│  │  ├─ components/       # 复用组件（SideNav、卡片等）
│  │  ├─ views/            # 页面视图（Dashboard、Audit、Events、Account...）
│  │  └─ router/           # 路由与登录态守卫
│  └─ vite.config.js
├─ backend/                # 后端（FastAPI）
│  ├─ services/            # 与 K8s 交互的服务层
│  ├─ main.py              # API 入口
│  └─ requirements.txt
└─ package.json            # 根级脚本代理到 frontend（便于在根目录运行）
```

## 快速开始

前提依赖：
- Node.js 18+ 与 npm
- Python 3.10+
- 可访问的 Kubernetes 集群（或本地 k3s/kind/minikube），并且提供 kubeconfig

1) 安装前端依赖并启动（在项目根目录执行）：
```bash
npm run install:frontend
npm run dev
```
默认使用 Vite 开发服务器，启动后按提示访问本地地址。首次进入请先登录（见下文“默认账号”）。

2) 启动后端服务：
```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

3) 配置 Kubernetes 访问（可选，若默认路径不可用需显式指定）：
后端通过环境变量 `KUBECONFIG_PATH` 指定 kubeconfig 路径，默认 `/etc/rancher/k3s/k3s.yaml`。
```bash
# Windows PowerShell 示例
$env:KUBECONFIG_PATH="D:\path\to\kubeconfig"
uvicorn backend.main:app --reload --port 8000
```

## 默认账号与鉴权说明
- 登录接口进行简单的内存态 Token 分发（原型实现）：
  - 用户名：`admin`
  - 密码：`admin123`
- 前端将 token 保存在 `localStorage` 的 `fc_token`，路由守卫在进入受保护页面时校验；退出登录会清除该 token。
- 后端在多数接口上通过 `Authorization: Bearer <token>` 或查询参数 `?token=<token>` 校验。

## 主要页面与交互路径
- `Login` → `Dashboard`：登录后跳转至仪表盘。
- `Audit`：展示风险项（配额缺失、特权、HostPath 等）。
- `Resources`：聚合 CPU/内存等使用情况。
- `Events`：SSE 实时事件流，按时间倒序。
- `FixAssistant`：基于审计项生成修复建议包与参数位。
- `ReportExport`：生成与预览周报 HTML。
- `Account`：显示当前用户与登录态状态、支持退出。

## 后端 API 概览（节选）
- `POST /auth/login`：登录，返回 token
- `POST /auth/logout`：退出登录
- `GET /auth/me`：当前用户信息
- `GET /k8s/overview`：集群总览
- `GET /k8s/audit`：审计结果
- `GET /k8s/resources/usage`：资源使用聚合
- `GET /k8s/security/advanced-scan`：高级安全扫描
- `GET /k8s/security/supply-chain`：供应链安全扫描
- `GET /k8s/security/top-alerts?limit=5`：高优先级告警
- `GET /k8s/fix/patch`：风险修复建议包
- `GET /k8s/reports/weekly-preview`：周报 HTML 预览
- `GET /k8s/events`：SSE 事件流

> 鉴权：除登录与健康检查外，其余接口均需携带有效 token。

## 构建与部署
前端构建：
```bash
npm run build
```
产物位于 `frontend/dist/`。可使用任意静态服务器或容器镜像进行部署。

后端部署：
- 以 Uvicorn/Gunicorn + Nginx 方式落地，或容器化部署。
- 需在运行环境中提供有效的 `KUBECONFIG_PATH`，并为服务账户配置必要的只读权限（建议最小权限原则）。

## 设计与实现说明（面向评审）
- 前后端分离，采用轻量技术栈（Vue 3 / FastAPI）降低样例工程的理解成本与复现实验；
- 后端将对 K8s 的具体交互（审计、事件、资源聚合、修复建议包生成）沉淀到 `services` 层，便于后续替换实现；
- 前端通过路由守卫实现最小登录态校验，并在 `Account` 页面中给出权限治理建议，呼应金融行业的内部审计与合规诉求；
- 事件通道选用 SSE，服务端易实现、浏览器端零依赖，足以覆盖本原型的实时性需求。

## 致谢与参考
- Kubernetes Python Client
- FastAPI / Uvicorn
- Vue 3 / Vite / Element Plus / ECharts



