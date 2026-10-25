# 架构

**简体中文** · [English](ARCHITECTURE.md) · [主页](../README.md)

VinaStudio 由四层组成，层与层之间边界严格。本文说明这套设计，以及更重要的——
决定其余一切的三条约束。

方法学验证、可复现性与参考文献见源码树的 `docs/ACADEMIC_VERIFICATION.md`。

```
┌──────────────────────────────────────────────────────────────┐
│ Qt 主线程                                                    │
│   QMainWindow · 原生菜单 · QWebChannel 桥                    │
│   ┌────────────────────────────────────────────────────┐     │
│   │ QWebEngineView（Chromium）                          │     │
│   │   Vue 3 SPA · Element Plus · 3Dmol.js              │     │
│   └────────────────────────────────────────────────────┘     │
├──────────────────────────────────────────────────────────────┤
│ 后台线程                                                     │
│   Uvicorn + FastAPI，监听 127.0.0.1:<临时端口>                │
│   REST /api/*  ·  WebSocket /ws  ·  StaticFiles（SPA）        │
├──────────────────────────────────────────────────────────────┤
│ spawn 出的子进程（multiprocessing，start method = spawn）     │
│   Vina 对接 · Meeko 参数化 · 网格生成                          │
└──────────────────────────────────────────────────────────────┘
```

| 层 | 位置 | 允许导入 |
|---|---|---|
| 桌面外壳 | `vinastudio/desktop/` | PySide6、`config`、`logging_setup` |
| API 服务 | `vinastudio/server/` | FastAPI、`core`、`schemas` |
| 领域核心 | `vinastudio/core/` | vina、meeko、rdkit、numpy —— **绝不**导入 Qt 或 FastAPI |
| 界面 | `web/` | 不导入任何 Python；只走 HTTP + WebSocket |

`core` 不依赖框架，所以科学逻辑可以脱离显示器与事件循环单独测试。

---

## 约束一：界面通过本地 HTTP 提供，绝不使用 `file://`

Vite 产物是 ES 模块。`file://` 没有源（origin），Chromium 会拒绝加载 ES 模块，
所以 `QWebEngineView.load(QUrl.fromLocalFile(…))` 只会得到白屏和 CORS 报错。

外壳因此在后台线程启动 Uvicorn，绑定 `127.0.0.1` 的 `0` 号端口（由内核挑一个
空闲端口），再把视图指向 `http://127.0.0.1:<port>`。端口 `0` 加上
`desktop/server_thread.py` 里的 `_PortReportingServer.startup` 钩子，就是 Qt 侧
得知实际端口的办法。

由此带来几个值得记住的结果：

- **API 与界面同源**，生产环境不需要 CORS。`server/app.py` 里的中间件只为
  5173 端口上的 Vite 开发服务器存在。
- **SSRF 面在构造上就不存在**：套接字只绑回环，从不绑 `0.0.0.0`。
- `web/vite.config.ts` 使用 **hash 路由**，所以深链接无论页面来自 `StaticFiles`
  还是 Vite 都能工作，不需要 SPA fallback 路由。

## 约束二：对接运行在 spawn 出来的子进程中

两个独立原因迫使进程隔离：

1. **Vina 无法取消。** `Vina.dock()` 是一次进入 C++ 的阻塞调用，没有中断接口。
   要让“取消”按钮真正生效，唯一办法是终止承载它的进程，所以对接循环不能与
   界面共用一个进程。
2. **这里不能用 `fork`。** 父进程持有运行中的 Qt 事件循环与 asyncio 循环。
   `fork` 会把两者都复制过去，子进程一碰就可能死锁。必须使用
   `multiprocessing.get_context("spawn")`——Linux 的默认启动方式是 `fork`。

进度来自 Vina 自己的 stdout。C++ 层会打印 `Computing Vina grid ... done.`、
`Performing docking (random seed: N) ...`、`0% .. 100%` 进度条，最后是
`mode | affinity | rmsd l.b. | rmsd u.b.` 表。worker 用 `os.dup2` 把文件描述符 1
重定向到作业日志，另开一条管道传结构化事件，再把两者转发给事件中心，由它经
`/ws` 广播。

因此 `verbosity` 不只是界面偏好：`verbosity=0` 时没有 stdout 可解析，进度会退化
成粗粒度的阶段切换。

**一个有记录的例外。** `POST /docking/score`、`/optimize` 与 `/randomize` 在 API
进程内建图并执行，因此既不可取消、也不隔离。它们服务于“对已有构象做交互式探索”：
每次调用是一个快速操作，而不是完整对接，界面会等待响应。它们自己计算亲和力地图，
所以会拒绝无法现场建图的打分函数（`ad4` 需要外部生成的 AutoGrid4 地图）。任何
更长的计算都属于 `/docking/start`。

## 约束三：PDBQT 绝不直接渲染

3Dmol.js 的 `addModel(data, format)` 接受 `pdb`、`sdf`、`xyz`、`pqr`、`mol2`、
`cif`、`mmtf`、`gro`、`prmtop` 与 `cube`，**没有 PDBQT**。把多余列删掉、伪装成
PDB 只会更糟：PDBQT 没有键级，也不含非极性氢，渲染器只能猜连通性。

受支持的路径正是 AutoDock 作者推荐的做法：

- **配体与构象** → Meeko 在它写出的每个 PDBQT 里留一行 `REMARK SMILES`。
  `mk_export` / `RDKitMolCreate.from_pdbqt_mol` 用这条 SMILES 重建 RDKit 分子，
  再把对接坐标拷上去，得到保留键级与形式电荷的 SDF；3Dmol 渲染这个 SDF。
- **受体** → `Polymer` / `mk_prepare_receptor.py` 可以把受体写回 PDB，3Dmol 能渲染
  PDB，卡通表示也需要它。

这也是应用能诚实地说“格式转换”，而不是暗地里塞一个键级猜测器的原因。

---

## 请求与事件流

```
        web (Vue)                        Qt 进程
           │                                  │
   用户操作                                 │
           ├──── HTTP /api/… ───────► FastAPI 路由
           │                            │  pydantic 校验
           │                            │  分发
           │                            ▼
           │                     spawn worker 进程
           │                            │  vina / meeko
           │                            │  结构化事件 ─┐
           │                            │  stdout → 作业日志 │
           │◄──── WS /ws ───────────────┴─────────────────────┘
           │
   响应式 store 更新 → 3Dmol 重绘
```

HTTP 做不到的原生能力——文件对话框、把 PNG 存到用户选定的位置、在文件管理器中
显示文件夹——走 **QWebChannel**。桥对象以 `bridge` 发布，由
`web/src/api/bridge.ts` 访问；在普通浏览器里它解析为 `null`，界面会降级而不是
崩溃。

反方向使用一个小型 JavaScript 命名空间：原生菜单调用
`window.vinastudio.<command>(...)`，在 `web/src/api/native.ts` 注册。语言与应用
状态始终以界面为唯一事实来源，所以 Qt 菜单的语言动作是请 Web 层切换，而不是
自己切。

---

## 分子管理器（旧版，Catalog 之前）

> 这一节记录 Catalog 之前的界面。`/molecules` 已由 `MoleculeCatalogView`
> 取代，旧的列表/详情组件已移除；当前架构见下一节。

分子管理器（`/molecules`）是侧栏里的独立视图，把上传、检查与准备分子文件收在
一个界面里。它取代了原先受体/配体各一套面板的做法，改成文件柜式的单页布局。

### 布局

```
┌──────────────────────────────────────────────────────────┐
│ MoleculeManagerView                                       │
│ ┌──────────────┬─────────────────────────────────────────┐│
│ │ MoleculePanel│  DetailPanel（flex-1）                   ││
│ │ (340–400px)  │  ┌─ vs-card ──────────────────────────┐ ││
│ │              │  │  header：名称 + 类型徽标              │ ││
│ │ ┌──────────┐ │  │  ┌─ ViewportCanvas ──────────────┐ │ ││
│ │ │上传按钮   │ │  │  │  3D 预览（PDB 或 SDF）         │ │ ││
│ │ │+ 提示    │ │  │  └───────────────────────────────┘ │ ││
│ │ └──────────┘ │  │  facts（原子/残基/链…）              │ ││
│ │ ┌──────────┐ │  │  notes（警告）                        │ ││
│ │ │受体       │ │  │  SMILES 块                           │ ││
│ │ │  ● 1iep  │ │  │  error 提示                          │ ││
│ │ ├──────────┤ │  │  report（原子 → 输出，chips）        │ ││
│ │ │配体       │ │  │  actions [检查][准备][移除]           │ ││
│ │ │  ● imat. │ │  └────────────────────────────────────┘ ││
│ │ ├──────────┤ │                                         ││
│ │ │未知       │ │                                         ││
│ │ └──────────┘ │                                         ││
│ │ [示例]       │                                         ││
│ └──────────────┴─────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Store 与数据流

`useMoleculeStore`（`web/src/stores/molecules.ts`）管理所有分子：

- `molecules: MoleculeItem[]` —— 主列表
- `activeId` —— 当前选中的分子
- `receptors / ligands / unknowns` —— 由 `getEffectiveType()` 计算
- `receptorPath / ligandPath` —— 各类型中第一个已准备/已检查的分子
- `filters / samples` —— 挂载时从后端加载

每个 `MoleculeItem` 有自己的状态机：

```
uploaded → inspecting → inspected → preparing → prepared
                ↓                      ↓
              error                  error
```

文件加载有两条路径：

- **桌面端**（`pickFiles`）：原生对话框返回文件系统路径；后端原地读取；
  `addFromPath()` + `inspectMolecule()` 自动判断类型。
- **浏览器端**（`pickFileForUpload`）：`<input type="file">` → `uploadAndAdd()`
  → POST `/api/files/upload` → 复制进工作区。

### 使用的界面模式

分子管理器与其他面板共用同一套设计系统：

- `vs-card` / `vs-card__header` / `vs-card__body` 作为卡片容器
- `facts` / `facts__row` / `facts__label` 作为属性行
- `report` / `report__title` / `chips` / `transforms` 展示准备结果
- `StatusPill`（内联 `.pill` 实现）表示状态
- `vs-mono` / `vs-mono-block` 表示等宽内容
- `notice` / `el-alert` 表示警告与错误
- `el-collapse` / `el-tag` 表示示例与选项

### 拖放

左侧面板接受文件拖放。拖入期间显示蓝色虚线边框；放下后自动上传并检查。

---

## 分子目录 Catalog（v2）

`/molecules` 现在读取工作区 Catalog，而不是旧 manifest。数据库位于
`<workspace>/catalog.sqlite`，保存分子身份、文件/产物、别名、标签、来源、
Study、集合、筛选库与 FTS5 索引；结构文件本身仍在磁盘上。

- **Study** 成员带角色（`receptor` / `ligand` / `cofactor`），一个 Study
  可包含多个受体；`study_members.is_primary` 只决定默认受体。
- **集合**是可嵌套的组织树，标签是多对多关系；两者都不能替代 Study 或筛选库。
- **筛选库**成员引用 Catalog 分子；创建/启动运行时物化为现有
  `libraries/<id>/mols/NNNNNN.sdf` 目录，供筛选 worker 使用。
- 配体身份用 InChIKey（父键单独保存），受体身份用 PDB ID 或内容哈希；
  路径不是身份。
- 检索在服务端完成（FTS5 + 结构化过滤），不再走旧的前端全量过滤。
- `molecules.json` 只作为一次性迁移/导出输入，复制为
  `molecules.json.pre-catalog`；旧 `/api/molecules` 仅保留兼容投影，不是
  第二写源。
- 只有 Study 的主受体与首个配体都已有 PDBQT 产物时，页面才会把它们接入
  现有对接管线。
- 文件、SMILES、2D 画板、示例、RCSB、PubChem、ChEMBL 都写入 Catalog；
  表格用 `ElTableV2` 虚拟渲染行并记住列显示配置，API 仍按页返回。

完整设计与当前边界见 [MOLECULE_CATALOG.zh-CN.md](MOLECULE_CATALOG.zh-CN.md)。

## 渲染与科学诚实

| 关注点 | 做法 |
|---|---|
| 蛋白质表示 | 由受体 PDB 生成 3Dmol 卡通；口袋残基用棍状 |
| 表面 | 3Dmol `addSurface`，类型限于界面暴露的 VDW/SAS/SES |
| 搜索盒 | 十二条边用线段绘制，语义与 Vina 一致（中心 + 边长） |
| 盒子预检 | 盒子内没有任何受体原子时，对接前直接拒绝；否则 Vina 会返回看似成功的全 0 构象 |
| 相互作用 | Python 里按几何距离与角度计算，用虚线圆柱绘制 |
| 静电势 | PDBQT 部分电荷的库仑求和投到网格，写成 Gaussian cube —— **明确标注为点电荷近似，绝不称为量子 ESP** |

对接不是坐标变换：Vina 收到的受体与盒子处于同一坐标系，`poses_to_sdf()`
把对接坐标原样写入 SDF。1iep 重对接基线会用共晶姿态核对结果（best-pose
RMSD 0.260 Å）。盒子完全在受体外是另一类失败：它会在启动前被拒绝，而不是
被记成一页 0.0 kcal/mol 的构象。该检查覆盖单次、批量、ensemble、筛选与
交互式 score/optimize/randomize 路径。

应用做不到的事情会直接写在界面上，而不是悄悄近似。最清楚的例子是 AutoDock4
打分：它需要 AutoGrid4 生成的亲和力地图，而 AutoGrid4 不随包分发，所以能力矩阵
把 `ad4` 标为 `nativeMaps: false`，两个对接表单都不提供它——目前没有办法提供
地图，一个只会失败的选项比没有选项更糟。`/docking/score`、`/optimize` 与
`/randomize` 出于同样原因拒绝它。

---

## 对接进度

Vina 1.2.7 只提供阶段，不提供可靠的实时百分比：Python API 与 CLI 都没有
per-step 回调，数字刻度通常在结束时才打印。因此单次对接显示“活动条 + 阶段
文字”（算地图 → 搜索 → 导出），不伪造 0/50/100；批量与筛选有真实的逐配体
完成计数，仍显示数字进度。

## 在线化合物来源

分子库保留 RCSB 的结构/共晶配体检索，并增加化合物 provider 层：

- **PubChem**（PUG REST）与 **ChEMBL**（REST）提供文本/ID、相似性、子结构检索。
  化学索引在来源服务端；应用不镜像数百万结构，也不在本地建 ANN 索引。
- 检索结果只在内存缓存 5 分钟，且只在用户触发时请求；PubChem 5 请求/秒、
  ChEMBL 更保守，统一由限流器串行化。
- 结果保留来源与许可；不同来源的 score 不比较。PubChem 提供 3D SDF；
  ChEMBL 公开 SDF 是 2D，必须先走正常准备流程才能对接。
- 旧 `/api/library/*` 的 RCSB 与 PubChem 快捷获取契约保持不变；新接口位于
  `/api/library/compounds/*`。

这是有意的产品边界：应用负责本地对接工作流，不负责重建化学搜索引擎或
镜像数据库。ZINC 没有稳定公开检索 API 且有人机验证，因此不作为在线来源；
BindingDB 的按靶点找配体留作后续适配，不在当前标签页中。

---

## 路线图

| 阶段 | 范围 | 状态 |
|---|---|---|
| 0 | 桌面外壳、回环 API、WebSocket、双语界面、环境自检、WebGL 视口 | 完成 |
| 1 | PDBQT 解析；Meeko 配体准备（MOL/SDF/MOL2 → PDBQT）；受体准备；PDBQT → SDF/PDB 导出；原生文件选择与上传兜底；已准备分子可渲染 | 完成 |
| 2 | 搜索盒编辑器与自动定盒；受体/配体样式；表面渲染 | 完成 |
| 3 | spawn 作业系统（实时进度、日志流、真取消）；完整打分/优化参数面 | 完成 |
| 4 | 构象排序、能量分解、相互作用检测、静电 cube、导出 | 完成 |
| 5 | 批量虚拟筛选、`.vinaproj` 项目文件 | 完成 |
| 6 | PyInstaller 打包 | 完成 |
| 7 | Windows 桌面包（安装包、命令行后端） | 完成 |
| 8 | 发布自动化、CI/测试门禁、Windows 硬化（0.5） | 下一步 |
| 9 | 结果深度：MM-GBSA/GNINA 调研、出版级图形（0.6） | 计划中 |
| 10 | 工作流与数据：数据管理、命令面板、可访问性（0.7） | 计划中 |
| 11 | 规模化：Docker/Web 模式、GPU 引擎（可行时）（0.8） | 计划中 |

### 平台支持

Linux 是主要的打包目标（`.deb` 与便携 tar.gz）。Windows 10 1809+ / 11 x64 从
**0.4.0** 起提供安装包，并已通过真机走查。该构建内置 AutoDock Vina 1.2.7
命令行引擎并自动使用它，因为上游从未发布 `vina` 模块的 Windows 轮子。准备、
对接、分析与持久化与 Linux 相同；面向用户的支持范围、已知边界（AutoDock4
地图、抗锯齿默认值、未签名安装包、仅 x64）与排障见 [WINDOWS.zh-CN.md](WINDOWS.zh-CN.md)。
macOS 仅保留源码路径，**不发布 release 包**（2026-10-21 决定）；不做安装包与
发布级验证。

### 工件与 `/artifacts` 挂载

每次准备都会在 `~/.vinastudio/workspace` 下得到自己的目录（`core/paths.py`），
API 返回工件 URL 而不是文件内容。一个准备好的受体 PDB 约 350 kB，不该塞进 JSON
响应；界面在渲染器需要时才去取，对接作业也把输出写到同一棵目录下。

挂载只暴露这个工作区，`StaticFiles` 拒绝路径穿越，所以它够不到应用没有写过的
任何东西。

### 受体管线必须先解决的两个问题

**残基在文件里被拆开。** Meeko 的解析器假设一个残基的原子是连续的。官方 1iep
参考文件的第二行有一个孤立的 `SER A 438` 的 `HB2`，该残基其余原子在文件末尾，
Meeko 0.8 会以“interrupted residues”拒绝整个结构。`normalise_pdb_atom_order`
把每个残基围绕它最大的连续块重新聚合——化学上无变化，且保持残基顺序——结果与
上游自己的 PDBQT 逐原子一致。

**与上游的差异。** 我们的受体与上游随包的那份并非逐字节相同，差异值得知道：
Meeko 现在把甲硫氨酸硫醚与半胱氨酸硫醇标为 `S`，旧版本用 `SA`，电荷约 -0.79
而不是 -0.10。元素计数、坐标与其他所有原子类型完全一致。测试钉住了量级，后续
变化不会悄悄通过；对打分的影响确认放在阶段 3。

---

## 值得刻意固定的依赖

- **`meeko >= 0.7.1`** —— 0.5/0.6 声明 `requires_python <3.12`，在本项目的
  Python 3.12 上装不了。
- **`gemmi`** —— Meeko 0.8.0 会在 `chemtempgen` 里导入 `gemmi`，但 PyPI 元数据
  完全没有声明依赖，所以必须显式列出，否则 `import meeko` 失败。
- **`web/` 里固定 TypeScript 5.x** —— TypeScript 7 不再提供 `vue-tsc` 需要的
  `lib/tsc`。TypeScript 只用于类型检查，Vite 自己剥离类型，固定 5.x 没有代价。
