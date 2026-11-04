# VinaStudio

**简体中文** · [English](README.en.md)

[![Release](https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release)](https://github.com/hubehero/VinaStudio/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg)](#安装与运行)
[![AutoDock Vina](https://img.shields.io/badge/AutoDock%20Vina-1.2.7-2f8f83)](https://github.com/ccsb-scripps/AutoDock-Vina)

VinaStudio 是 AutoDock Vina 的桌面界面。Vina 仍然负责对接计算；VinaStudio
负责准备受体和配体、设置结合位点、启动任务、查看结果，并把每次任务真正使用的
参数、输入和日志留在作业记录里。适合需要反复跑同一套流程、又不想每次重写命令
的人。

![VinaStudio 界面总览](https://github.com/user-attachments/assets/52492a9f-e995-40f5-bf5b-4ff35f6c4bc9)

图中左上为对接结果，右上为工作台，左下为分子目录，右下为结果汇报。

## 功能

- 受体 PDB/mmCIF 转 PDBQT；配体 MOL/SDF/MOL2/SMILES 转 3D PDBQT，使用 Meeko。
- 从配体或残基推导盒子，也可以手动输入中心和尺寸，并在 3D 视图中调整。
- 使用 Vina、Vinardo 或 AutoDock4 对接，显示运行阶段、日志，支持中途取消。
- 查看姿态、逐姿态能量分解、Redocking RMSD、几何检查和 2D/3D 相互作用图。
- 用 Catalog 管理受体、配体、Study、集合和筛选库；自带 125 个常用药物条目。
- 导出 CSV、pose、HTML 报告和项目文件；历史记录支持收藏、标签和比较。

## 结构速览

<details open>
<summary><strong>vinastudio/</strong> · Python 应用</summary>
<ul>
  <li><code>desktop/</code>：Qt 窗口、原生菜单、QWebChannel 文件桥</li>
  <li><code>server/</code>：FastAPI、JobManager、WebSocket 事件</li>
  <li><code>core/</code>：准备、对接、分析；不依赖 Qt 或 FastAPI
    <details>
      <summary>展开 core</summary>
      <ul>
        <li><code>chem/</code>：配体/受体准备、PDBQT、导出、相互作用</li>
        <li><code>catalog/</code>：SQLite Catalog、检索、迁移</li>
        <li><code>engines/</code>：Vina CLI 适配</li>
        <li><code>worker.py</code>：spawn 子进程入口</li>
      </ul>
    </details>
  </li>
  <li><code>schemas/</code>：请求/响应模型</li>
  <li><code>resources/</code>：内置 1IEP 样本与验证资源</li>
</ul>
</details>

<details>
<summary><strong>web/</strong> · Vue 3 SPA</summary>
<ul>
  <li><code>src/views/</code>：工作台、分子目录、盒子、对接、结果</li>
  <li><code>src/stores/</code>：Pinia 状态</li>
  <li><code>src/components/</code>：面板、3D 视口、对话框、画板</li>
  <li><code>src/api/</code>：HTTP、WebSocket、QWebChannel</li>
</ul>
</details>

<details>
<summary><strong>docs/</strong> · 文档与结构图谱</summary>
<ul>
  <li><a href="docs/structure.html">HTML 树状图谱</a>：完整、可展开的视觉版</li>
  <li><a href="docs/STRUCTURE.zh-CN.md">结构图谱文字版</a>：运行结构、对接流程和路径表</li>
</ul>
</details>

<details>
<summary><strong>validation/</strong> · 验证与基准</summary>
<ul>
  <li><code>functional/</code>：1IEP 对照、功能矩阵、UI 证据</li>
  <li><code>benchmark/</code>：开放集协议、清单、PoseBusters 记录</li>
</ul>
</details>

<details>
<summary><strong>scripts/</strong> · 构建与验证工具</summary>
<ul>
  <li><code>dev.py</code>：API + Vite + Qt 热重载</li>
  <li><code>build_web.py</code>：构建界面</li>
  <li><code>fetch_samples.py</code>：获取并校验 1IEP 样本</li>
</ul>
</details>

运行时，Qt 主线程和 FastAPI 后台线程在同一个桌面进程；对接单独跑在 spawn 子进程里，所以“取消”可以真正终止计算。上面的树可直接展开；完整视觉版是 [HTML 结构图谱](docs/structure.html)，GitHub 会显示它的源码，下载后用浏览器打开。

## 安装

### Windows

从 [Releases](https://github.com/hubehero/VinaStudio/releases) 下载
`vinastudio-<版本>-setup.exe` 和 `SHA256SUMS`，核对 SHA-256 后运行。安装器按
机器安装，需要管理员权限，且未签名，SmartScreen 会要求确认。它已经带上
Python、科学计算依赖和 Vina 1.2.7 命令行引擎。

Windows 的限制见 [Windows 支持](docs/WINDOWS.zh-CN.md)：AutoDock4 需要外部
地图，抗锯齿默认关闭，只支持 x64，也没有自动更新。

### Linux

从 Releases 下载 `.deb` 或便携 tar.gz。`.deb` 用
`sudo apt install ./vinastudio_<版本>_amd64.deb` 安装；tar.gz 解压后运行
`vinastudio/vinastudio`。

### 从源码运行

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22+ 和
[pnpm](https://pnpm.io/)。

```bash
pnpm -C web install
pnpm -C web build            # 先构建界面，生成 vinastudio/server/static
uv sync --extra dev
uv run python -m vinastudio
```

## 跑一遍 1IEP

1. 打开应用，在工作台点「一键准备 1iep 示例」。
2. 检查受体、配体和自动生成的盒子，进入「分子对接」。
3. 保持默认 Vina、exhaustiveness 8、20 poses，点「开始对接」。
4. 在结果页查看姿态和相互作用，在「结果汇报」里查看本次参数和图表。

这是软件流程的对照样例，不代表一般对接准确率。更多操作见
[用户手册](docs/USER_GUIDE.zh-CN.md)。

## 验证

仓库里保留了实际运行记录：

- 1IEP 重对接：top pose RMSD 0.353 Å，最佳亲和力 −13.286 kcal/mol，
  5 个姿态，0 个几何错误。
- 12 个预注册开放靶点 × 5 个随机种子：60/60 通过，平均 top-1 RMSD
  0.5343 Å，bootstrap 95% 置信区间 [0.4710, 0.6020] Å。
- 官方 PoseBusters 0.6.5（`redock`，与对接使用同一套制备结果）：
  top pose 60/60 通过，全部 pose 7/60 通过。

这些结果只对应上述开放集合和协议，不能外推成 PDBbind/CASF 结果、通用准确率、
富集能力或实验结合自由能。协议、失败记录和原始报告在
[学术验证](docs/ACADEMIC_VALIDATION.zh-CN.md) 和
[基准记录](validation/benchmark/records/2026-11-02-open-posebusters-v1/)。

## 实现

代码分为四层：

| 层 | 位置 | 职责 |
|---|---|---|
| 桌面外壳 | `vinastudio/desktop/` | Qt 窗口、原生菜单、QWebChannel 桥 |
| API | `vinastudio/server/` | 回环 FastAPI，托管界面，推送任务事件 |
| 核心 | `vinastudio/core/` | 准备、对接和分析，不依赖 Qt 或 FastAPI |
| 界面 | `web/` | Vue 3 + 3Dmol.js |

界面通过本地 HTTP 提供，不使用 `file://`；对接在 spawn 出来的子进程中运行，
因为 Vina 没有取消接口；PDBQT 不直接渲染，而是交给 Meeko 转成 SDF。原因和
实现细节在[架构文档](docs/ARCHITECTURE.zh-CN.md)。

## 文档

- [用户手册](docs/USER_GUIDE.zh-CN.md) · [English](docs/USER_GUIDE.md)
- [文档索引](docs/README.md) · [Windows 支持](docs/WINDOWS.zh-CN.md)
- [学术验证与范围](docs/ACADEMIC_VALIDATION.zh-CN.md)
- [验证方法与复现](docs/VALIDATION.md)
- [更新记录](CHANGELOG.md) · [贡献指南](CONTRIBUTING.zh-CN.md) ·
  [安全策略](SECURITY.zh-CN.md)

## 开发

下面的命令需要开发树；公开 release tree 不带测试和 `scripts/dev.py`。

```bash
uv run python scripts/dev.py   # API + Vite + Qt，热重载
./web_start.sh                 # 只开 Web 界面
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## 许可

代码使用 MIT 许可证，见 [LICENSE](LICENSE)。第三方声明见
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

主要依赖和参考项目：[AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)、
[Meeko](https://github.com/forlilab/Meeko)、[RDKit](https://www.rdkit.org/)、
[3Dmol.js](https://3dmol.csb.pitt.edu/)、[Vue 3](https://vuejs.org/)、
[Element Plus](https://element-plus.org/)、
[PySide6](https://doc.qt.io/qtforpython/)。
