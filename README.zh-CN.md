# VinaStudio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![AutoDock Vina](https://img.shields.io/badge/AutoDock-Vina-1.2.7-green.svg)](https://vina.scripps.edu/)

基于 **AutoDock Vina** 的现代化分子对接桌面工作台，提供图形化界面进行受体/配体准备、结合位点定义、对接执行和结果分析。

**A modern desktop workbench for AutoDock Vina molecular docking.**

[English Documentation](README.md) | [User Guide](docs/USER_GUIDE.md) | [Architecture](docs/ARCHITECTURE.md)

---

## 功能特性

- **受体与配体准备** — PDB/CIF/mmCIF → PDBQT（受体），MOL/SDF/MOL2/PDB → PDBQT（配体），基于 Meeko
- **结合位点定义** — 自动或手动设置对接盒子，支持 3D 可视化
- **分子对接** — 支持 Vina、Vinardo 和 AutoDock4 打分函数，完整参数控制
- **批量对接** — 处理多个配体，支持 CSV 导出
- **结果分析** — 姿态排序、能量分解、相互作用检测（氢键、疏水、离子）
- **3D 可视化** — 交互式分子查看器，多种表示样式
- **RCSB PDB 集成** — 直接从 PDB 数据库下载受体和配体
- **项目管理** — 保存和恢复对接项目
- **中英双语** — 支持中文和英文界面

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

## 开发路线

- [x] 受体和配体准备
- [x] 对接盒子配置
- [x] Vina/Vinardo 对接与进度跟踪
- [x] 批量对接与 CSV 导出
- [x] 3D 可视化与相互作用分析
- [x] RCSB PDB 数据库集成
- [x] 项目管理
- [ ] SMILES 输入支持
- [ ] 2D 分子编辑器
- [ ] 2D 相互作用图
- [ ] ADMET 预测
- [ ] 柔性残基对接
- [ ] Docker 部署

## 致谢

本项目基于以下开源软件构建：

- **[AutoDock Vina](https://vina.scripps.edu/)** — The Scripps Research Institute 开发的分子对接引擎。采用 [Apache License 2.0](https://github.com/ccsb-scripps/AutoDock-Vina/blob/develop/LICENSE) 许可。
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

所有代码均经过人类开发者审查、测试和验证。

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 MIT 许可证 — 详见 [LICENSE](LICENSE)。

**注意：** 本项目使用 AutoDock Vina，其采用 Apache License 2.0。Apache License 2.0 与 MIT 许可证兼容。使用或分发本软件时，用户必须遵守两个许可证的条款。

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
