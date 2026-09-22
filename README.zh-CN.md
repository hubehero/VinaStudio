# VinaStudio

面向 **AutoDock Vina** 的现代化桌面工作台：Vue 3 + 3Dmol.js 界面运行在
**PySide6** 内嵌浏览器中，后端直接使用官方 `vina` Python API，分子参数化与
格式转换由 **Meeko** 完成。

English documentation: [README.md](README.md)
**用户手册（零基础可学）**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)

---

## 这是什么

AutoDock Vina 本身很优秀，但只有命令行界面，且其 Python API 是一组阻塞调用。
VinaStudio 把两者包装成一个好用的桌面应用，同时保持科学上的严谨：

- **受体与配体准备** —— 受体 PDB/CIF → PDBQT；配体 MOL/SDF/MOL2 → PDBQT，
  全部经由 Meeko。对于只有 2D 坐标或缺氢的输入，会先补氢并生成 3D 构象再参数化。
- **结合位点定义** —— 可由配体或残基选择自动推导包围盒，也可手动输入中心与尺寸，
  在 3D 中实时渲染与编辑。
- **分子对接** —— 支持 Vina、Vinardo 与 AutoDock4 三种打分函数，暴露完整参数面，
  提供实时进度、流式日志与真正的取消功能。
- **结果分析** —— 姿态排序、逐姿态能量分解、几何相互作用检测（氢键、盐桥、
  π-π 堆积、疏水接触）并以 3D 标注绘制。
- **中英双语** —— 默认中文，可切换英文。

## 环境要求

- Linux / macOS / Windows
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ 与 [pnpm](https://pnpm.io/)（仅用于构建界面）

## 安装与运行

```bash
uv sync --extra dev          # 创建 .venv 并安装科学计算依赖
pnpm -C web install          # 安装界面依赖
pnpm -C web build            # 构建界面到 vinastudio/server/static
uv run python -m vinastudio  # 启动桌面应用
```

`scripts/build_web.py` 封装了上面两条 pnpm 命令。

## 开发

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

三条约束决定了其余设计，详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：

1. 界面通过**本地 HTTP** 提供，绝不使用 `file://` —— 文件协议下 ES 模块会被 CORS 拦截。
2. 对接运行在 **spawn 出来的子进程**中 —— Vina 没有取消接口，杀进程是唯一的中止方式；
   而 `fork` 与运行中的 Qt 事件循环共存是不安全的。
3. **PDBQT 绝不直接渲染** —— 3Dmol.js 不解析该格式，且 PDBQT 不携带键级。
   姿态由 Meeko 转为 SDF，从 PDBQT 头部记录的 SMILES 还原键级与形式电荷。

## 当前状态

项目分阶段构建。目前已经可用的部分：

- 桌面外壳：Vue 界面、原生菜单、QWebChannel 桥
- 中英双语界面与主题切换
- 环境自检：真实导入 `vina`、`meeko`、`rdkit`
- **配体准备** —— MOL/SDF/MOL2/PDB → PDBQT，经由 Meeko，并报告补了多少氢、
  是否生成了 3D 构象、检出多少可旋转键。可逐字节复现上游 1iep 参考 PDBQT。
- **受体准备** —— PDB → PDBQT，使用 Meeko 的模板匹配；可按需删除水分子与非聚合物
  基团、拆出柔性侧链，并包含官方 1iep 示例所需的残基原子归位。
- **渲染** —— 准备好的受体以卡通显示、配体以棒状显示在同一视口中，运行于
  QtWebEngine 内的 WebGL 之上。
- 桌面端使用原生文件对话框，浏览器端有上传兜底。

对接与分析功能将在后续阶段落地，路线图见
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 许可证

MIT
