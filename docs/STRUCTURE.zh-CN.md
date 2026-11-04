# 项目结构图谱

**简体中文** · [English](STRUCTURE.md) · [主页](../README.md)

**视觉版：** [structure.html](structure.html) — 完整的树状页面，下载后用浏览器打开。GitHub 只会显示 HTML 源码，不直接渲染这个文件。

这页用文字树、表格和步骤说明结构；先看运行结构，再看一次对接怎么走，最后查代码位置和 Catalog 关系。

## 怎么读

| 你有多少时间 | 看哪里 |
|---|---|
| 30 秒 | [运行结构](#运行结构)：哪些东西在同一个进程里 |
| 5 分钟 | [对接生命周期](#一次对接的生命周期)：请求、事件和取消 |
| 想改代码 | [代码结构](#代码结构)：按职责找目录 |
| 改 Catalog | [Catalog 关系](#catalog-关系)：分子、Study、集合和筛选库 |

## 运行结构

<details open>
<summary><strong>桌面进程（同一个 Python 进程）</strong></summary>
<ul>
  <li><details open>
    <summary><strong>Qt 主线程</strong>：窗口、界面和原生能力</summary>
    <ul>
      <li><code>PySide6 外壳</code>：主窗口、原生菜单</li>
      <li><code>QWebEngineView</code>：Vue 3 + 3Dmol.js</li>
      <li><code>QWebChannel</code>：文件对话框、保存、打开目录</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><strong>后台线程</strong>：本地 API</summary>
    <ul>
      <li><code>FastAPI</code>：REST <code>/api/*</code> 与 WebSocket <code>/ws</code></li>
      <li><code>JobManager</code>：提交、事件、取消、作业恢复</li>
      <li><code>EventHub</code>：向 SPA 广播任务事件</li>
    </ul>
  </details></li>
</ul>
</details>

<details open>
<summary><strong>spawn 子进程</strong>：按任务启动</summary>
<ul>
  <li><code>worker.py</code>：stdout 解析、Pipe 事件</li>
  <li><code>AutoDock Vina 1.2.7</code> · <code>Meeko</code> · <code>RDKit</code></li>
</ul>
</details>

<details open>
<summary><strong>工作区</strong>：唯一持久化位置</summary>
<ul>
  <li><code>jobs/</code>：作业产物、日志、<code>job.json</code></li>
  <li><code>projects/</code>：<code>.vinaproj</code> 项目文件</li>
  <li><code>catalog.sqlite</code>：分子、Study、集合、筛选库</li>
</ul>
</details>

关键点：

- Qt 主线程和 FastAPI 后台线程在同一个桌面进程里；API 不是独立服务。
- 对接单独跑在 spawn 子进程里。Vina 没有取消接口，所以取消就是终止该 job 的所有 worker。
- Web 只通过 HTTP 和 WebSocket 访问 Python；原生文件能力走 QWebChannel。
- RCSB、PubChem、ChEMBL 是 API 的可选外部来源，不属于本地结构。

## 一次对接的生命周期

1. Vue 调 `POST /api/docking/start`，立即拿到 job id。
2. JobManager 启动 spawn worker，分配独立事件 Pipe。
3. worker 调 Vina/Meeko；stdout 重定向到作业日志。
4. 结构化事件经 Pipe → JobManager → EventHub → WebSocket 回到界面。
5. 完成后写 `job.json` 和工件；取消则终止该 job 的所有 worker。

单次对接通常一个 worker；批量和筛选按分片启动多个 worker，每个 worker 有自己的事件管道。

## 代码结构

<details open>
<summary><strong>vinastudio/</strong> · Python 应用</summary>
<ul>
  <li><details open>
    <summary><code>desktop/</code>：Qt 外壳、原生菜单、QWebChannel、后台服务线程</summary>
    <ul>
      <li><code>main_window.py</code>：窗口与菜单命令</li>
      <li><code>server_thread.py</code>：后台 Uvicorn 与端口回传</li>
      <li><code>bridge.py</code>：原生文件能力桥</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><code>server/</code>：FastAPI、JobManager、WebSocket、routers</summary>
    <ul>
      <li><code>app.py</code>：应用装配、静态 SPA、错误映射</li>
      <li><code>job_manager.py</code>：spawn、Pipe、取消、作业恢复</li>
      <li><code>ws.py</code>：EventHub 与 <code>/ws</code> 广播</li>
      <li><code>routers/</code>：system、files、catalog、docking、screening 等</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><code>core/</code>：准备、对接、分析；不依赖 Qt 或 FastAPI</summary>
    <ul>
      <li><code>chem/</code>：配体/受体准备、PDBQT、导出、相互作用、画板</li>
      <li><code>catalog/</code>：SQLite Catalog、检索、迁移、种子</li>
      <li><code>engines/</code>：Vina CLI 适配</li>
      <li><code>worker.py</code>：spawn 子进程入口</li>
      <li><code>box.py</code> / <code>docking.py</code>：盒子与对接领域逻辑</li>
      <li><code>workspace.py</code> / <code>paths.py</code> / <code>results_db.py</code>：工作区、路径、结果索引</li>
    </ul>
  </details></li>
  <li><code>schemas/</code>：Pydantic 请求/响应契约</li>
  <li><code>resources/</code>：内置 1IEP 样本与验证资源</li>
</ul>
</details>

<details open>
<summary><strong>web/</strong> · Vue 3 SPA</summary>
<ul>
  <li><code>src/views/</code>：工作台、分子目录、盒子、对接、结果</li>
  <li><code>src/stores/</code>：Pinia 状态</li>
  <li><code>src/components/</code>：面板、3D 视口、对话框、画板</li>
  <li><code>src/api/</code>：HTTP、WebSocket、QWebChannel</li>
  <li><code>src/types/api.ts</code>：后端契约的 TypeScript 镜像</li>
</ul>
</details>

<details open>
<summary><strong>仓库级目录</strong></summary>
<ul>
  <li><code>docs/</code>：架构、用户指南、验证、结构图谱</li>
  <li><code>validation/</code>：可复现验证与基准记录</li>
  <li><code>scripts/</code>：构建、开发、采样、验证工具</li>
  <li><code>sample/</code>：额外样本；原始数据按需获取</li>
</ul>
</details>

| 想改什么 | 先看哪里 |
|---|---|
| 桌面窗口、原生菜单、文件对话框 | `vinastudio/desktop/` |
| API 路由、请求/响应模型 | `vinastudio/server/routers/`、`vinastudio/schemas/` |
| 任务提交、取消、事件广播 | `vinastudio/server/job_manager.py`、`ws.py` |
| 对接、盒子、准备、分析 | `vinastudio/core/` |
| 子进程入口、stdout 解析 | `vinastudio/core/worker.py` |
| 页面、交互、状态 | `web/src/views/`、`stores/`、`components/` |
| 前端接口类型 | `web/src/types/api.ts` |

## Catalog 关系

| 关系 | 含义 |
|---|---|
| `molecules → molecule_files` | 一个分子有多个来源/准备文件；文件不是身份 |
| `molecules → aliases / tags / sources` | 名称、标签和来源是分子的附属信息 |
| `studies → study_members → molecules` | Study 成员带 `role`（受体/配体/辅因子）和 `is_primary` |
| `collections → collection_members → molecules` | 集合是可嵌套的组织树，不替代 Study |
| `libraries → library_members → molecules` | 筛选库引用 Catalog 分子，成员带 `entry_index` |

分子身份由 `identity_key` 决定；一个分子可以同时出现在多个 Study、集合和筛选库中。数据库位于 `<workspace>/catalog.sqlite`，结构文件仍在工作区磁盘上。

## 相关文档

- [交互式体验文档](https://hubehero.github.io/VinaStudio/experience/)
- [架构与三条约束](ARCHITECTURE.zh-CN.md)
- [分子目录设计](MOLECULE_CATALOG.zh-CN.md)
- [用户手册](USER_GUIDE.zh-CN.md)
- [文档索引](README.md)
