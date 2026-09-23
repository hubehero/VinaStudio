# VinaStudio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![AutoDock Vina 1.2.7](https://img.shields.io/badge/AutoDock-Vina-1.2.7-green.svg)](https://vina.scripps.edu/)

VinaStudio 是一款围绕 [AutoDock Vina 1.2.7](https://vina.scripps.edu/) 构建的图形化桌面应用，目标是让研究人员和学生能够快速上手分子对接，而不需要记忆复杂的命令行参数或手动编辑配置文件。

在传统的对接流程中，受体准备、配体参数化、盒子设置、运行对接、查看结果往往分散在不同的工具里。VinaStudio 把这些步骤整合到了一个窗口中：加载 PDB 或 SDF 文件，可视化地定义结合位点，一键启动对接，然后直接浏览按亲和力排序的构象、能量分解和相互作用图谱。

应用桌面端基于 PySide6 (Qt)，前端使用 Vue 3 单页应用，两者通过本地 REST API 通信。支持 Linux、macOS 和 Windows 平台。

> **说明：** VinaStudio 定位于初学者学习和探索性研究，尚未经过大规模基准数据集的验证，不建议作为论文中的主要工具引用。如需进行正式的对接研究，请直接使用 AutoDock Vina 或经过验证的工作流程。

[English Documentation](README.md) | [用户指南](docs/USER_GUIDE.md) | [架构文档](docs/ARCHITECTURE.md)

---

## 功能特性

- **受体与配体准备** — PDB/CIF/mmCIF → PDBQT（受体），MOL/SDF/MOL2/PDB → PDBQT（配体），基于 Meeko，支持删除水分子、去除非聚合物基团、重排原子顺序
- **结合位点定义** — 自动按配体或受体重原子计算盒子，也可手动输入中心和尺寸，支持 3D 可视化
- **分子对接** — 支持 Vina、Vinardo 和 AutoDock4 打分函数，完整参数控制（穷举度、随机种子、能量范围等）
- **批量对接** — 逐个处理多个配体，带进度跟踪和 CSV 导出
- **结果分析** — 按亲和力排序构象、RMSD 聚类、能量分解，以及氢键、疏水、离子相互作用检测
- **3D 可视化** — 基于 3Dmol.js 的交互式分子查看器，支持卡通、棒状、球状和表面表示
- **RCSB PDB 集成** — 直接从 PDB 数据库搜索并下载受体和配体
- **项目管理** — 以 `.vinaproj` 文件保存和恢复完整的对接会话
- **中英双语** — 支持中文和英文界面，可随时切换
- **API 文档** — 内置 Swagger UI，可通过设置对话框访问

## 环境要求

- Linux / macOS / Windows
- Python 3.12
- [uv](https://docs.astral.sh/uv/)（包管理器）
- Node.js 20+ 与 [pnpm](https://pnpm.io/)（构建前端）

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/hubehero/VinaStudio.git
cd VinaStudio

# 安装依赖
uv sync --extra dev

# 构建前端
pnpm -C web install
pnpm -C web build

# 启动应用
uv run python -m vinastudio
```

## 开发

热重载模式运行：

```bash
uv run python scripts/dev.py
```

运行测试和检查：

```bash
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## 架构

| 层 | 位置 | 说明 |
|----|------|------|
| 桌面外壳 | `vinastudio/desktop/` | PySide6 窗口，原生菜单，QWebChannel 桥接 |
| API 服务 | `vinastudio/server/` | FastAPI 回环服务，WebSocket 作业流 |
| 领域核心 | `vinastudio/core/` | 对接、准备和分析逻辑 |
| 前端界面 | `web/` | Vue 3 + 3Dmol.js 单页应用 |

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 支持格式

| 类型 | 输入格式 |
|------|----------|
| 配体 | `.sdf`, `.mol`, `.mol2`, `.pdb`, `.pdbqt` |
| 受体 | `.pdb`, `.cif`, `.mmcif`, `.ent`, `.pdbqt` |

## 致谢

本项目基于以下开源软件构建：

- **[AutoDock Vina 1.2.7](https://vina.scripps.edu/)** — The Scripps Research Institute 开发的分子对接引擎。采用 [Apache License 2.0](https://github.com/ccsb-scripps/AutoDock-Vina/blob/develop/LICENSE) 许可。
- **[Meeko](https://github.com/forlilab/Meeko)** — AutoDock Vina 分子准备工具。采用 [Apache License 2.0](https://github.com/forlilab/Meeko/blob/master/LICENSE) 许可。
- **[RDKit](https://www.rdkit.org/)** — 化学信息学工具包。采用 [BSD 3-Clause](https://github.com/rdkit/rdkit/blob/master/license.txt) 许可。
- **[3Dmol.js](https://3dmol.org/)** — 分子可视化库。采用 [MIT License](https://github.com/3dmol/3Dmol.js/blob/master/LICENSE) 许可。
- **[Vue.js](https://vuejs.org/)** — 渐进式 JavaScript 框架。采用 [MIT License](https://github.com/vuejs/vue/blob/dev/LICENSE) 许可。
- **[PySide6](https://doc.qt.io/qtforpython-6/)** — Qt for Python。采用 [LGPL](https://doc.qt.io/qtforpython-6/license.html) 许可。
- **[FastAPI](https://fastapi.tiangolo.com/)** — 现代 Python Web 框架。采用 [MIT License](https://github.com/fastapi/fastapi/blob/master/LICENSE) 许可。

### AI 辅助开发

本项目在开发过程中使用了 [Claude](https://claude.ai/)（Anthropic 开发的 AI 助手）进行辅助。Claude 用于：

- 代码生成与重构
- Bug 识别与调试
- 文档编写
- 架构设计讨论
- 测试用例开发

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 MIT 许可证 — 详见 [LICENSE](LICENSE)。

**注意：** 本项目使用 AutoDock Vina 1.2.7，其采用 Apache License 2.0。Apache License 2.0 与 MIT 许可证兼容。使用或分发本软件时，用户必须遵守两个许可证的条款。

## 引用

如果您在研究中使用 VinaStudio，请引用：

```bibtex
@software{vinastudio2026,
  title = {VinaStudio: A Modern Desktop Workbench for AutoDock Vina},
  year = {2026},
  url = {https://github.com/hubehero/VinaStudio}
}
```

以及底层工具：

```bibtex
@article{trott2010,
  title = {AutoDock Vina: Improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading},
  author = {Trott, Oleg and Olson, Arthur J.},
  journal = {Journal of Computational Chemistry},
  volume = {31},
  number = {2},
  pages = {455--461},
  year = {2010}
}
```

---

**免责声明：** 本软件仅供科学研究和教育目的。用户需自行承担使用本软件进行分子对接研究的风险和责任。
