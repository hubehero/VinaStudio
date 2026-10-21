# VinaStudio

**简体中文** · [English](README.en.md)

[![Release](https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release)](https://github.com/hubehero/VinaStudio/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg)](#环境要求)

面向 **AutoDock Vina** 的现代化桌面工作台：Vue 3 + 3Dmol.js 界面运行在
**PySide6** 内嵌浏览器中，后端使用官方 **AutoDock Vina 1.2.7** 引擎——有
Python 模块时走 API，Windows 上走随包命令行二进制——分子参数化与格式转换由
**Meeko** 完成。

**文档入口：** [用户手册](docs/USER_GUIDE.zh-CN.md) · [Windows 支持](docs/WINDOWS.zh-CN.md) · [架构](docs/ARCHITECTURE.zh-CN.md) · [更新记录](CHANGELOG.md)
**English:** [README.en.md](README.en.md) · [User guide](docs/USER_GUIDE.md) · [Windows](docs/WINDOWS.md)

## 文档

| 文档 | 简体中文 | English |
|---|---|---|
| 用户手册（从安装到导出） | [用户手册](docs/USER_GUIDE.zh-CN.md) | [User guide](docs/USER_GUIDE.md) |
| Windows 支持与边界 | [Windows 支持](docs/WINDOWS.zh-CN.md) | [Windows](docs/WINDOWS.md) |
| 架构与三条约束 | [架构](docs/ARCHITECTURE.zh-CN.md) | [Architecture](docs/ARCHITECTURE.md) |
| 更新记录 | [CHANGELOG.md](CHANGELOG.md) | 双语 |
| 贡献指南 | [贡献指南](CONTRIBUTING.zh-CN.md) | [Contributing](CONTRIBUTING.md) |
| 行为准则 | [行为准则](CODE_OF_CONDUCT.zh-CN.md) | [Code of conduct](CODE_OF_CONDUCT.md) |
| 安全策略 | [安全策略](SECURITY.zh-CN.md) | [Security](SECURITY.md) |
| 发布流程 | [发布流程](RELEASING.zh-CN.md) | [Releasing](RELEASING.md) |
| 许可证 | MIT | [LICENSE](LICENSE) |

应用运行时会在本机提供 API 文档：**/docs**。

---

## 这是什么

AutoDock Vina 本身很优秀，但只有命令行界面，且其 Python API 是一组阻塞调用。
VinaStudio 把两者包装成一个好用的桌面应用，同时保持科学上的严谨。它面向需要
反复做受体准备、定义盒子、对接与结果复盘的研究生和实验组：命令行的每一步都在
同一个窗口里完成，每次运行实际使用的参数也会随结果留存。

主要能力：

- **受体与配体准备** —— 受体 PDB/CIF → PDBQT；配体 MOL/SDF/MOL2 → PDBQT，
  全部经由 Meeko。对于只有 2D 坐标或缺氢的输入，会先补氢并生成 3D 构象再参数化。
- **结合位点定义** —— 可由配体或残基选择自动推导包围盒，也可手动输入中心与尺寸，
  在 3D 中实时渲染与编辑。
- **分子对接** —— 支持 Vina、Vinardo 与 AutoDock4 三种打分函数，暴露完整参数面，
  提供实时进度、流式日志与真正的取消功能。
- **结果分析** —— 姿态排序、逐姿态能量分解、几何相互作用检测（氢键、盐桥、
  疏水接触）并以 3D 标注绘制，另附 2D 相互作用图。
- **结构输入** —— SMILES 生成 3D 配体；内置 **2D 画板**（模板环、链工具、
  键级/立体、一键整理、周期表与自由基），绘制闭环直到导出使用。
- **中英双语** —— 默认中文，可切换英文。

## 环境要求

| 平台 | 可用形态 |
|---|---|
| Linux（x86_64） | `.deb` 与便携 tar.gz，已发布 |
| Windows 10 1809+ / 11（x64） | 安装包，已通过真机走查；**0.4.0 起**正式发布 |
| macOS | 仅源码运行，未打包、未做发布级验证 |

从源码运行需要 Python 3.12、[uv](https://docs.astral.sh/uv/)，以及
Node.js 20+ 与 [pnpm](https://pnpm.io/)（仅用于构建界面）。Windows 安装包
已内置这些运行时与 Vina 引擎，用户无需另装。

## 安装与运行

### Windows

从[发布页](https://github.com/hubehero/VinaStudio/releases)下载
`vinastudio-<版本>-setup.exe`，核对 SHA-256 后运行。安装包按机器安装
（需要管理员权限）且未签名，SmartScreen 会要求确认。它内置 AutoDock Vina
1.2.7 命令行引擎，应用会自动使用它——上游 `vina` Python 模块没有 Windows 版。

支持范围与需要知道的边界（AutoDock4 地图、抗锯齿默认值、未签名安装包、
仅 x64）见 [docs/WINDOWS.zh-CN.md](docs/WINDOWS.zh-CN.md)。

### 从源码运行

```bash
uv sync --extra dev          # 创建 .venv 并安装科学计算依赖
pnpm -C web install          # 安装界面依赖
pnpm -C web build            # 构建界面到 vinastudio/server/static
uv run python -m vinastudio  # 启动桌面应用
```

`scripts/build_web.py` 封装了上面两条 pnpm 命令。

## 开发

以下命令需要开发树：发布镜像只分发应用与打包产物，不含测试套件与 `scripts/dev.py`。

以热重载方式运行界面，并连接真实 API：

```bash
uv run python scripts/dev.py
```

该脚本会在固定回环端口启动 API、启动 Vite 开发服务器，并让 Qt 窗口指向 Vite。
修改 `web/src` 下任意文件，窗口会即时更新，无需重启。

运行检查：

```bash
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## 架构

四层，边界严格：

| 层 | 位置 | 职责 |
|---|---|---|
| 桌面外壳 | `vinastudio/desktop/` | Qt 窗口、原生菜单、QWebChannel 桥 |
| API 服务 | `vinastudio/server/` | 回环上的 FastAPI，托管单页应用，用 WebSocket 推送作业事件 |
| 领域核心 | `vinastudio/core/` | 对接、准备与分析逻辑 —— 不依赖 Qt 与 FastAPI，可完全单元测试 |
| 界面 | `web/` | 由内嵌 Chromium 渲染的 Vue 3 单页应用 |

三条约束决定了其余设计，详见 [docs/ARCHITECTURE.zh-CN.md](docs/ARCHITECTURE.zh-CN.md)：

1. 界面通过**本地 HTTP** 提供，绝不使用 `file://` —— 文件协议下 ES 模块会被 CORS 拦截。
2. 对接运行在 **spawn 出来的子进程**中 —— Vina 没有取消接口，杀进程是唯一的中止方式；
   而 `fork` 与运行中的 Qt 事件循环共存是不安全的。
3. **PDBQT 绝不直接渲染** —— 3Dmol.js 不解析该格式，且 PDBQT 不携带键级。
   姿态由 Meeko 转为 SDF，从 PDBQT 头部记录的 SMILES 还原键级与形式电荷。

## 当前状态

项目分阶段构建。目前已经可用的部分：

- 桌面外壳（PySide6 + 内嵌 Chromium）、中英双语与主题切换、环境自检
  （真实导入 `vina`/`meeko`/`rdkit`）
- **配体准备** —— MOL/SDF/MOL2/PDB → PDBQT，经由 Meeko，并报告补了多少氢、
  是否生成了 3D 构象、检出多少可旋转键。可逐字节复现上游 1iep 参考 PDBQT。
- **受体准备** —— PDB/mmCIF → PDBQT，使用 Meeko 的模板匹配；可按需删除水分子
  与非聚合物基团、拆出柔性侧链，并包含官方 1iep 示例所需的残基原子归位。
- **盒子与对接** —— 自动/手动包围盒（3D 中渲染可编辑）；Vina、Vinardo 与
  AutoDock4 打分，spawn 子进程作业带实时进度、流式日志与真取消；批量对接
  与排行榜。
- **结果分析** —— 构象几何体检、Redocking RMSD 对照、RMSD 聚类、2D 相互
  作用图、逐姿态能量分解。
- **持久化与导出** —— 作业历史与项目保存/重启恢复、自包含 HTML 结果包、
  独立「结果汇报」页。
- **结构输入** —— SMILES 生成 3D 配体；内置 2D 画板（见上）；分子管理器
  批量检查与准备。
- **渲染诊断** —— GPU/软件渲染可见、画质分档；桌面原生文件对话框，
  浏览器端上传兜底。
- **Windows 桌面包** —— 安装包由 CI 构建并通过真机走查（准备、对接、分析、
  持久化、中文路径）。对接使用随包的 Vina 1.2.7 命令行引擎；抗锯齿因
  QtWebEngine Windows 合成器的闪屏问题默认关闭。边界与排障见
  [docs/WINDOWS.zh-CN.md](docs/WINDOWS.zh-CN.md)。

路线图见 [docs/ARCHITECTURE.zh-CN.md](docs/ARCHITECTURE.zh-CN.md)。

## 社区

- **问题与缺陷：** 请在 [GitHub Issues](https://github.com/hubehero/VinaStudio/issues)
  提交，并附上版本、操作系统、环境自检页的渲染器原文，以及相关日志片段。
- **参与贡献：** 先读 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。
- **行为准则：** [CODE_OF_CONDUCT.zh-CN.md](CODE_OF_CONDUCT.zh-CN.md)。
- **安全：** 按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md) 私下报告，请不要在公开
  issue 里贴利用细节。

项目由一位维护者与贡献者共同推进；issue 与 PR 都会看，但回复可能需要几天。

## 参考项目与致谢

VinaStudio 站在开源生态之上。以下组件为直接依赖，或作为有据可查的
行为/规格参考（licenses 指上游项目自身）：

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
  （Apache-2.0）—— 对接引擎。
- [Meeko](https://github.com/forlilab/Meeko)（LGPL-2.1）—— 配体与受体
  PDBQT 参数化。
- [RDKit](https://www.rdkit.org/)（BSD-3-Clause）—— 化学信息学、SMILES
  处理与 2D 绘制。
- [3Dmol.js](https://3dmol.csb.pitt.edu/)（BSD-3-Clause）—— WebGL 分子
  查看器。
- [MoleditPy](https://pypi.org/project/moleditpy/)（**GPL-3.0**）—— 内置
  画板的 2D 绘制**交互模型**（指针语义、快捷键、渲染约定）以其实现为
  行为规格参考。VinaStudio 画板是独立的 Vue 3 + SVG 重新实现，**未包含、
  链接或分发任何 MoleditPy 源代码**，亦未以其为依赖。
- [Vue 3](https://vuejs.org/)（MIT）、[Element Plus](https://element-plus.org/)
  （MIT）—— 界面框架与组件库。
- [PySide6](https://doc.qt.io/qtforpython/)（LGPL-3.0）—— Qt for Python
  桌面外壳。

## 许可证

MIT（见 [LICENSE](LICENSE)）
