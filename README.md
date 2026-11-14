<h1 align="center">VinaStudio</h1>

<p align="center"><strong>AutoDock Vina 的桌面工作台</strong></p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>

<p align="center">准备分子、定义盒子、运行对接、复盘结果，并把每次任务真正使用的参数和日志留在同一条记录里。</p>

<p align="center">
  <a href="https://github.com/hubehero/VinaStudio/releases"><img src="https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="#安装"><img src="https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg" alt="Platforms"></a>
  <a href="https://www.python.org/downloads/release/python-3120/"><img src="https://img.shields.io/badge/python-3.12-3776AB" alt="Python 3.12"></a>
  <a href="https://github.com/ccsb-scripps/AutoDock-Vina"><img src="https://img.shields.io/badge/AutoDock%20Vina-1.2.7-2f8f83" alt="AutoDock Vina"></a>
  <a href="https://hubehero.github.io/VinaStudio/experience/"><img src="https://img.shields.io/badge/docs-GitHub%20Pages-2f8f83" alt="Documentation"></a>
</p>

<p align="center">
  <a href="https://hubehero.github.io/VinaStudio/experience/">交互式体验</a> ·
  <a href="docs/USER_GUIDE.zh-CN.md">用户手册</a> ·
  <a href="docs/ARCHITECTURE.zh-CN.md">架构</a> ·
  <a href="docs/ACADEMIC_VALIDATION.zh-CN.md">验证</a> ·
  <a href="https://github.com/hubehero/VinaStudio/releases">Releases</a>
</p>

---

<details>
<summary><strong>目录</strong> · 17 个章节</summary>

| 开始 | 使用 | 深入 |
|---|---|---|
| [项目简介](#项目简介) | [安装](#安装) | [验证](#验证) |
| [项目概览](#项目概览) | [跑通 1IEP](#跑通-1iep) | [工作原理](#工作原理) |
| [界面预览](#界面预览) | [常见问题](#常见问题) | [项目结构](#项目结构) |
| [功能](#功能) | [文档](#文档) | [开发](#开发) |
| [贡献](#贡献) | [引用](#引用) | [安全](#安全) |
| [许可证](#许可证) | [致谢](#致谢) | [Releases](https://github.com/hubehero/VinaStudio/releases) |

</details>

## 项目简介

VinaStudio 是 [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina) 的桌面工作台。对接计算仍然由 Vina 完成；VinaStudio 负责把周围那条容易出错的流程固定下来：

- 把受体和配体转换成 Vina 能读取的 PDBQT；
- 从配体、残基或候选口袋推导搜索盒子，也可以手动调整；
- 用 Vina、Vinardo 或 AutoDock4 启动任务，查看阶段和日志，必要时真正取消；
- 把姿态、能量、RMSD、几何检查和相互作用放在同一个结果页；
- 把本次任务使用的参数、输入哈希、引擎版本和种子保存在作业记录里。

它适合需要反复跑同一套流程、比较多个配体，或者不想每次重新拼命令行的用户。

> [!NOTE]
> VinaStudio 不实现新的打分函数，也不把对接分数解释成实验结合自由能。不同打分函数的能量不能直接比较；界面和报告会保留这个边界。

## 项目概览

| 项目 | 说明 |
|---|---|
| **对接引擎** | AutoDock Vina 1.2.7；Vinardo；AutoDock4（需要外部 AutoGrid4 地图） |
| **输入** | 受体：PDB、mmCIF；配体：MOL、SDF、MOL2、PDB、SMILES，以及内置 2D 画板 |
| **搜索空间** | 配体/残基推导、候选口袋、手动中心和尺寸；3D 视图内调整 |
| **结果** | 姿态查看、逐姿态能量分解、Redocking RMSD、几何检查、2D/3D 相互作用图 |
| **组织** | Catalog：分子、文件、Study、集合、筛选库，内置 125 个常用药物条目 |
| **导出** | PDBQT/SDF、CSV、HTML 报告、`.vinaproj` 项目文件、作业记录 |
| **平台** | Linux x86_64、Windows 10 1809+/11 x64；macOS 可从源码尝试，未提供发布包 |
| **界面** | PySide6 桌面外壳、Vue 3 SPA、3Dmol.js、回环 FastAPI |

## 界面预览

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/docking.png" alt="对接结果：姿态、能量分解和相互作用" width="900">
</p>

<p align="center"><sub>对接结果：姿态、能量分解和相互作用</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/workbench.png" alt="工作台：准备、盒子和对接步骤" width="900">
</p>

<p align="center"><sub>工作台：准备、盒子和对接步骤</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/molecules.png" alt="分子目录：分子、Study、集合和筛选库" width="900">
</p>

<p align="center"><sub>分子目录：分子、Study、集合和筛选库</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/report.png" alt="结果汇报：参数、图表和历史任务" width="900">
</p>

<p align="center"><sub>结果汇报：参数、图表和历史任务</sub></p>

交互式导览覆盖准备、盒子、对接生命周期、Catalog 和验证记录：[打开交互式导览](https://hubehero.github.io/VinaStudio/experience/)。


## 功能

### 分子准备

- 受体从 PDB/mmCIF 进入 Meeko 的 Polymer 路径，可保留指定水分子、金属和辅因子，并按需拆分柔性侧链。
- 配体从 MOL/SDF/MOL2/PDB/SMILES 读入；没有 3D 坐标时用 RDKit 生成构象并补氢。
- 准备报告列出补氢、3D 构象、可旋转键、删除/保留的基团以及被忽略的残基。
- PDBQT 只保留重原子和极性氢；原子数下降是格式行为，不是数据丢失。

### 盒子与位点

- 从配体、残基或候选结合位点推导盒子；
- 手动输入中心和尺寸，在 3D 视图中检查和调整；
- 启动前检查盒子是否包含受体原子，避免把空盒子跑成一页看似成功的 `0.0` 构象；
- 支持单配体对接、批量对接和按位点筛选。

### 对接与结果

- Vina、Vinardo 和 AutoDock4 三条路径；
- 运行阶段、stdout 日志、WebSocket 事件和可取消的 spawn 子进程；
- 姿态排序、亲和力、逐姿态能量分解、Redocking RMSD；
- 几何检查、聚类、相互作用指纹和 2D/3D 相互作用图；
- 作业历史中的参数、输入哈希、引擎版本、种子和日志。

### 组织与导出

- Catalog 管理分子身份、文件、Study、集合和筛选库；
- 项目文件保存准备产物和当前管线，重新打开时可以继续；
- 导出 CSV、pose、HTML 报告和结果包，便于在论文或报告中使用。

## 安装

### Windows

从 [Releases](https://github.com/hubehero/VinaStudio/releases) 下载
`vinastudio-<version>-setup.exe` 和 `SHA256SUMS`，核对 SHA-256 后运行。
发布页同时提供 `BUILD-MANIFEST.json`，记录 tag、commit、CI 运行和每个资产的 SHA-256；它是来源记录，不是签名。

安装器按机器安装，需要管理员权限，且**未签名**，SmartScreen 会要求确认。安装包已经带上 Python、科学计算依赖和 Vina 1.2.7 命令行引擎；支持 Windows 10 1809+ / 11 x64。

Windows 的边界见 [Windows 支持](docs/WINDOWS.zh-CN.md)：AutoDock4 需要外部地图、抗锯齿默认关闭、只支持 x64，没有自动更新。

### Linux

从 Releases 下载 `.deb` 或便携 `.tar.gz`：

```bash
# Debian / Ubuntu
sudo apt install ./vinastudio_<version>_amd64.deb

# 便携包
tar -xzf vinastudio_<version>_linux_amd64.tar.gz
./vinastudio/vinastudio
```

### 从源码运行

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22+ 和 [pnpm](https://pnpm.io/)。

```bash
pnpm -C web install
pnpm -C web build            # 生成 vinastudio/server/static
uv sync --extra dev
uv run python -m vinastudio
```

如果只改界面，也可以先运行 `pnpm -C web dev`，用 Vite 的热更新连接本地 API。

## 跑通 1IEP

[1IEP](https://www.rcsb.org/structure/1IEP) 是项目一直使用的对照样例：c-Abl 激酶与伊马替尼。它能完整走通准备、盒子、对接、结果和报告。

1. 打开应用，在工作台点 **「一键准备 1iep 示例」**。
2. 检查受体、配体和自动生成的盒子；需要时在 3D 视图中微调。
3. 进入 **「分子对接」**，保持默认 Vina、`exhaustiveness=8`、20 poses。
4. 开始对接，观察阶段和日志；需要停止时使用取消。
5. 在结果页查看姿态、能量分解和相互作用，在结果汇报页检查本次参数和图表。

这是软件流程的对照样例，不代表一般对接准确率。完整步骤见[用户手册](docs/USER_GUIDE.zh-CN.md)。

## 验证

仓库保留实际运行记录，不用一张成功截图代替验证：

| 记录 | 结果 |
|---|---|
| 1IEP 重对接 | top pose RMSD **0.353 Å**；最佳亲和力 **−13.286 kcal/mol**；5 个姿态；0 个几何错误 |
| 12 个预注册开放靶点 × 5 seeds | **60/60** 通过；平均 top-1 RMSD **0.5343 Å**；bootstrap 95% CI **[0.4710, 0.6020] Å** |
| 官方 PoseBusters 0.6.5（`redock`） | top pose **60/60**；全部 pose **7/60** |

> [!IMPORTANT]
> 这些数字只对应预注册的开放集合、协议和输入制备方式。它们不是 PDBbind/CASF 结果，也不能外推成通用准确率、富集能力或实验结合自由能。

协议、失败记录、原始报告和参考文献：

- [学术验证与范围](docs/ACADEMIC_VALIDATION.zh-CN.md)
- [验证方法与复现](docs/VALIDATION.md)
- [开放基准记录](validation/benchmark/records/2026-11-02-open-posebusters-v1/)
- [基准协议](validation/benchmark/PROTOCOL.md)

## 工作原理

VinaStudio 分为四层，边界是刻意画死的：

| 层 | 位置 | 职责 |
|---|---|---|
| 桌面外壳 | `vinastudio/desktop/` | Qt 窗口、原生菜单、QWebChannel 文件桥 |
| API | `vinastudio/server/` | 回环 FastAPI、静态 SPA、REST、WebSocket 和 JobManager |
| 领域核心 | `vinastudio/core/` | 准备、盒子、对接、分析、Catalog；不导入 Qt 或 FastAPI |
| 界面 | `web/` | Vue 3 + 3Dmol.js；只通过 HTTP + WebSocket 访问 Python |

有三条约束决定了实现方式：

1. **界面通过本地 HTTP 提供，不使用 `file://`。** ES 模块在 `file://` 下没有可用 origin；Qt 启动 Uvicorn 绑定 `127.0.0.1:0`，再把 WebView 指向实际端口。
2. **对接在 spawn 子进程中运行。** Vina 没有取消接口，终止进程是唯一可靠的停止方式；父进程持有 Qt 和 asyncio 循环，不能用 `fork`。
3. **PDBQT 不直接渲染。** 3Dmol 不解析 PDBQT，也没有键级；姿态由 Meeko 转成 SDF 后再显示。

完整的运行结构、进程边界和对接生命周期见[架构文档](docs/ARCHITECTURE.zh-CN.md)与[结构图谱](https://hubehero.github.io/VinaStudio/structure.html)。

## 项目结构

<details>
<summary><strong>展开仓库目录</strong></summary>

```text
vinastudio/
├── desktop/          Qt 窗口、原生菜单、WebChannel、Uvicorn 线程
├── server/           FastAPI、路由、JobManager、WebSocket
├── core/             分子准备、盒子、对接、结果分析、Catalog
│   ├── chem/         PDBQT、RDKit/Meeko、相互作用、导出
│   ├── catalog/      SQLite Catalog、检索、迁移
│   ├── engines/      Vina CLI 适配
│   └── worker.py     spawn 子进程入口
├── schemas/          请求 / 响应模型
└── resources/        1IEP 样本与验证资源

web/                  Vue 3 SPA
├── src/views/        工作台、分子、盒子、对接、结果
├── src/stores/       Pinia 状态
├── src/components/   面板、3D 视口、对话框、画板
└── src/api/          HTTP、WebSocket、QWebChannel

docs/                 用户、架构、Catalog、Windows 文档和结构图谱
docs/experience/      可交互的 Pages 体验文档
validation/           1IEP 对照、功能矩阵、开放基准和 PoseBusters 记录
scripts/              构建、样本、验证和诊断工具
tests/                单元测试与集成测试
```

</details>

## 文档

| 主题 | 文档 |
|---|---|
| 安装、准备、对接、分析和导出 | [用户手册](docs/USER_GUIDE.zh-CN.md) · [English](docs/USER_GUIDE.md) |
| 运行结构、进程和对接生命周期 | [结构图谱](https://hubehero.github.io/VinaStudio/structure.html) · [文字版](docs/STRUCTURE.zh-CN.md) |
| 四层架构与三条硬约束 | [架构](docs/ARCHITECTURE.zh-CN.md) · [English](docs/ARCHITECTURE.md) |
| 分子、文件、Study、集合和筛选库 | [Catalog](docs/MOLECULE_CATALOG.zh-CN.md) |
| 方法、结果、失败记录和参考 | [学术验证](docs/ACADEMIC_VALIDATION.zh-CN.md) · [English](docs/ACADEMIC_VALIDATION.md) |
| Windows 安装、限制和诊断 | [Windows 支持](docs/WINDOWS.zh-CN.md) · [English](docs/WINDOWS.md) |
| 可点击的原理与功能导览 | [Interactive Field Guide](https://hubehero.github.io/VinaStudio/experience/) |

完整索引见 [`docs/README.md`](docs/README.md)。

## 常见问题

### 为什么准备后原子数变少了？

PDBQT 只保留重原子和极性氢，非极性氢会被去掉。准备报告会列出补氢、3D 构象和保留/删除的基团；这是格式转换的结果，不是文件损坏。

### 为什么 AutoDock4 不能直接开始对接？

AutoDock4 需要 AutoGrid4 预先生成的亲和力地图。项目不捆绑 AutoGrid4，也不会在后台伪造地图；没有地图时请使用 Vina 或 Vinardo。详见 [Windows 限制](docs/WINDOWS.zh-CN.md) 和[架构文档](docs/ARCHITECTURE.zh-CN.md)。

### 对接分数可以当作结合自由能吗？

不可以。Vina、Vinardo 和 AutoDock4 都是简化模型上的打分函数；分数用于同一协议内的相对排序，不是实验测得的 ΔG。

### Windows 上 3D 视图闪烁怎么办？

QtWebEngine 6 的 WebGL 合成器在部分 Windows 显卡上会闪烁，项目默认关闭 3Dmol 抗锯齿。可在 **Settings → Rendering quality** 中调整；这是渲染问题，不影响对接计算。

### 作业和项目文件在哪里？

首次启动会选择工作区，作业写入 `<workspace>/jobs/`，项目写入 `<workspace>/projects/`。完成的作业会保留参数、输入哈希、引擎版本、seed 和日志。

## 开发

从源码运行应用：

```bash
pnpm -C web install
pnpm -C web build
uv sync --extra dev
uv run python -m vinastudio
```

开发与检查命令：

```bash
uv run python scripts/dev.py   # API + Vite + Qt，热重载
./web_start.sh                 # 只启动 Web 界面
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web build:checked
```

科学逻辑应留在 `vinastudio/core/`，不要依赖 Qt 或 FastAPI；用户可见的文案改动需要同时更新 `web/src/i18n/locales/zh-CN.ts` 和 `en-US.ts`。

公开的 release tree（`vina_simple/`）有意不包含 Python 测试套件；上面的 `pytest` 命令作用于开发树。开发树包含 900 多项单元与集成测试，1IEP 对照和验证记录见[验证](#验证)与[学术验证](docs/ACADEMIC_VALIDATION.zh-CN.md)。

## 贡献

欢迎可复现的 bug 报告、聚焦的修复和文档改进。提交 PR 前：

- 先搜索已有 issue，避免重复；
- 说明操作系统、版本、复现步骤和相关日志；
- 一次 PR 只处理一个问题；
- 行为变更同步更新 `CHANGELOG.md`；
- 能运行的检查尽量在本地跑完。

详见 [贡献指南](CONTRIBUTING.zh-CN.md) · [English](CONTRIBUTING.md) 和 [行为准则](CODE_OF_CONDUCT.zh-CN.md)。

## 引用

如果 VinaStudio 对研究工作有帮助，请引用软件和它所实现的方法。仓库提供 [`CITATION.cff`](CITATION.cff)，也可以在 GitHub 的 **Cite this repository** 中生成引用格式。

主要方法文献包括 AutoDock Vina 原始论文、Meeko 和 RDKit；完整参考文献与 claim-evidence 对照见[学术验证](docs/ACADEMIC_VALIDATION.zh-CN.md)。

## 安全

VinaStudio 完全在本机运行：Qt 窗口、回环 FastAPI 和 spawn 子进程。API 只接受同源状态变更，WebSocket 握手单独校验，上传接口要求自定义请求头。

如果发现安全问题，请不要公开提交细节；使用 GitHub Security 的私密报告渠道，见 [安全策略](SECURITY.zh-CN.md)。

## 许可证

代码使用 [MIT License](LICENSE)。第三方组件和许可证见
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

## 致谢

VinaStudio 建立在以下开源项目之上：

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)：对接引擎
- [Meeko](https://github.com/forlilab/Meeko)：PDBQT 参数化与姿态转换
- [RDKit](https://www.rdkit.org/)：分子读取、构象和化学工具
- [3Dmol.js](https://3dmol.csb.pitt.edu/)：分子可视化
- [Vue 3](https://vuejs.org/) 与 [Element Plus](https://element-plus.org/)：界面
- [PySide6](https://doc.qt.io/qtforpython/)：桌面外壳
