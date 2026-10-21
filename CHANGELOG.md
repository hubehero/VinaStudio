# Changelog

面向使用者的变更记录。格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)（0.y.z 期间
任何内容都可能变动）。**发布说明由本文件对应小节生成**，请只写面向用户的功能与
影响，不要写内部任务编号或工作流叙述。

User-facing changes. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (during 0.y.z anything
may change). **Release notes are generated from the matching section below**, so keep
entries about the product — no internal task ids or workflow narration.

## [Unreleased]

## [0.4.0] - 2026-10-21

自 v0.3.0（2026-10-14）以来的全部交付。质量基线：pytest 711 全绿 / ruff 0 /
`vue-tsc` 0，1iep 金标准全链路回归与 Windows 冻结包内的真对接冒烟均在册。

### 新增

- **在 Windows 上安装项目不再失败**：`vina` 模块没有 Windows 版，此前它是**硬依赖**，
  导致 `pip install` 直接报错；现在它只在该平台存在时才是依赖。应用在 Windows 上通过随包的
  命令行二进制对接（见下一条）。
- **安装包内附带官方 Vina 二进制**：桌面包（deb / tar.gz）把它放在
  `vinastudio/resources/vina/`，因此 `vina` Python 模块缺失或损坏的机器**仍能对接**——这正是
  命令行后端存在的意义。二进制为 Apache-2.0，署名随包同行；它不进 wheel（wheel 面向该平台
  必有模块的 `pip` 用户）。
- **对接后端自动选择**：装不上 `vina` Python 模块的机器（典型是 Windows）会自动改用**官方
  命令行二进制**——同一个 1.2.7 引擎、同一套参数（固定种子下两者结果逐构象一致）。「环境
  自检」页新增一行，显示当前后端**以及为什么**（是模块还是二进制、是否被环境变量指定），
  出问题时能一眼看出谁在跑。
- **Windows 桌面版（0.4.0）**：提供 x64 安装包，内置 Python 运行时、科学栈与
  AutoDock Vina 1.2.7 命令行引擎；已在真实 Windows 机器上完成准备、对接、分析、
  持久化与中文路径走查。支持范围与边界见 `docs/WINDOWS.zh-CN.md`。
- **Windows 构建内真对接冒烟**：每个 Windows 包都会在冻结环境里跑一次 1iep
  （穷举度 1），断言作业完成、至少一个构象、亲和力为负——这类“能导入但不能跑”
  的问题不会再静默出厂。

### 变更

- **抗锯齿默认关闭**：QtWebEngine 6 在 Windows 上的 WebGL 合成器存在无规律闪屏，
  且抗锯齿会把绘制缓冲放大到 2 倍（像素数 4 倍）；默认关闭以保证稳定，设置里可随时
  重新打开。旧设置会自动迁移一次，之后手动选择保留。
- **Windows 运行期不再弹出 `vina.exe` 控制台窗口**：子进程以无窗口方式启动，
  进度仍通过 stdout 管道回传，日志与进度条不受影响。

### 修复

- **Windows 冻结包对接停在 0%**：安装包此前没有把 spawn 子进程交给
  `multiprocessing` 的冻结入口，子进程会重新启动整个 GUI，作业永远停在 0%。
  现在入口先调用 `freeze_support()`，作业正常开始并完成。
- **窗口版没有 stdout 时 worker 启动失败**：改为在无 fd 1 时也能建立进度管道。
- **中文/非 ASCII 路径下配体读取失败**：RDKit 改为按字节流读取，路径不再经过
  窄字符 API。
- **交互式「优化」与「随机化」修好**：这两个操作此前拿不到构象（「优化」更是直接失败），
  根因是调用了写**对接**构象的那个接口。现在两条路径都返回真实构象，「优化」另返回能量。
  随机化的种子输入框已移除：引擎的随机化不接受种子、结果无法复现（两条路径皆然），
  留着输入框等于假承诺，现在改为一句如实说明。
- 加固本机 API 的来源策略：状态变更请求若声明了**外来 `Origin`**（含 `Origin: null`）
  一律拒绝，WebSocket 握手同样检查；上传端点（唯一的非 JSON 请求体，也是浏览器唯一
  会**免预检**发出的请求）额外要求一个自定义头。不带 `Origin` 的请求（curl、脚本、
  测试客户端）照旧放行——功能与命令行用法不变。

### 已知边界

- **Windows**：AutoDock4 仍需外部 AutoGrid4 地图；抗锯齿默认关闭（上游 QtWebEngine
  的 Windows WebGL 合成器存在无规律闪屏）；安装包未签名、无自动更新、安装器界面为
  英文；仅 x64，不支持 ARM64 / Windows 7/8。支持范围与排障见 `docs/WINDOWS.zh-CN.md`。
- **macOS**：仍只有源码运行路径，没有安装包，也未做发布级验证。

### Added

- **Installing the project on Windows no longer fails**: `vina` has no Windows build
  and was a hard dependency, which made `pip install` impossible there. It is now a
  dependency only where it exists; on Windows the application docks through the
  packaged command-line binary instead.
- **The official Vina binary now ships inside the desktop packages**: the deb and the
  tarball carry it at `vinastudio/resources/vina/`, so a machine whose `vina` Python
  module is missing or broken can still dock — the whole reason the command-line
  backend exists. It is Apache-2.0 with its attribution alongside, and it stays out
  of the wheel, which serves `pip` users on platforms where the module exists.
- **Automatic docking backend**: a machine without the `vina` Python module (Windows,
  typically) falls back to the **official command-line binary** — the same 1.2.7 engine
  with the same parameters (with a fixed seed the two agree pose for pose). The
  environment page now names the backend **and why** (module or binary, and whether the
  environment forced it), so a surprising run can be traced to the door it used.
- **Windows desktop build (0.4.0)**: an x64 installer that bundles the Python
  runtime, the scientific stack and the AutoDock Vina 1.2.7 command-line engine;
  preparation, docking, analysis, persistence and non-ASCII paths were walked
  through on real hardware. Scope and boundaries: `docs/WINDOWS.md`.
- **A real docking smoke in the Windows build**: every Windows package now docks
  1iep once (exhaustiveness 1) inside the frozen bundle and asserts completion,
  at least one pose and a negative affinity, so "imports but cannot run" cannot
  ship silently again.

### Changed

- **Antialiasing is off by default**: QtWebEngine 6 on Windows has an
  intermittent WebGL compositor flicker, and AA doubles 3Dmol's draw buffer
  (4× the pixels). Off by default for stability; the switch re-enables it.
  Older settings migrate once, then an explicit choice sticks.
- **No `vina.exe` console window while running**: the child starts windowless;
  its stdout pipe still carries progress, so logs and the progress bar are
  unaffected.

### Fixed

- **Windows frozen builds stuck at 0%**: the packaging entry point never handed
  spawn children to `multiprocessing`'s frozen entry, so a child restarted the
  whole GUI and the job never left 0%. The entry point now calls
  `freeze_support()` before parsing arguments.
- **Workers failed when a windowed build had no stdout**: the progress pipe is
  now established without assuming fd 1 exists.
- **Ligands failed to read from non-ASCII paths**: RDKit now reads through byte
  streams instead of the narrow-character path APIs.
- **Interactive "optimise" and "randomise" work again**: neither could return a
  conformation (optimise failed outright) because both asked the writer that serves
  **docking** poses. Both doors now hand back the real pose, optimise with its energy,
  and the randomise seed field is gone: the engine takes no seed for randomisation and
  no run can be reproduced, so the field was a promise it could not keep.
- Hardened the local API's origin policy: a state-changing request that announces a
  foreign `Origin` (including `Origin: null`) is refused, the WebSocket handshake is
  checked the same way, and the upload endpoint — the only non-JSON body, and therefore
  the only request a browser sends without a preflight — additionally requires a custom
  header. Requests without an `Origin` (curl, scripts, tests) behave exactly as before.

### Known boundaries

- **Windows**: AutoDock4 still needs externally generated AutoGrid4 maps;
  antialiasing is off by default because of the upstream QtWebEngine Windows WebGL
  compositor flicker; the installer is unsigned, has no auto-update, and its
  installer UI is English; x64 only, no ARM64 or Windows 7/8. Scope and
  troubleshooting: `docs/WINDOWS.md`.
- **macOS** remains source-only: no package and no release-level verification.

## [0.3.0] - 2026-10-14

自 v0.2.0（2026-09-27）以来的全部交付。质量基线：pytest 627 全绿 / ruff 0 /
`vue-tsc` 0，1iep 金标准全链路回归在册。

### 新增

- **虚拟筛选工作台**：导入小分子库（SDF / MOL / SMILES）→ 逐分子对接 → 排行榜；
  每行带 QED 与 Lipinski 违规数，导入有大小上限，失败逐行标注，中断后可续跑。
- **批量并行对接**：一个受体对多个配体，可指定并行度；逐配体结果行与 CSV 导出。
- **结果数据库**：跨任务的配体、能量与命中检索，随工作区持久化。
- **相互作用指纹（IFP）与姿态聚类**：残基 × 相互作用类型的矩阵视图，把构象按 RMSD 分簇。
- **序列视图与柔性残基点选**：查看受体序列，勾选柔性残基直接用于对接设置。
- **类药性 / ADMET-lite 面板**：QED、Lipinski、基本描述符汇总，可导出。
- **按名称取 3D 构象（PubChem）**：输入化合物名即可获得可对接的 3D 结构。
- **候选结合位点检测**：只凭受体几何找出候选空腔（按 fpocket 论文的 alpha 球方法），
  每个候选给出可直接使用的对接盒；也支持 mmCIF 受体。
- **位点筛选（逐点对接排序）**：把同一个配体分别对接进每个候选盒，按最佳亲和力
  排序，并对选中位点一键定盒。这是**粗筛**：排序只在本次候选之间成立，数值不可与
  标准参数的正式对接结果直接比较。
- **应用内帮助与术语表**：按「你在做什么」分组的常见问题，术语表解释反复出现、
  容易误解的概念（含已知边界，例如几何方法找不到的位点）。
- **入门导读**：工作台按流水线给出步骤状态与「下一步」，并可一键装载 1iep 示例。
- **Methods 段落生成**：按任务**实际运行**的参数生成方法学段落，可直接粘进论文；
  未记录的旧任务会明示缺参，不编造。

### 变更

- **对接页与结果汇报页职责分离**：对接页负责「运行与检视」，报告页负责「复盘与导出」，
  两页互相可达；重复内容移除。
- **视图比例与信息层级**：对接舞台恒占 ≥62% 宽度，操作面板自适应（380–520 px）；
  结果页重排为「概览 → 构象 → 分析 → 校验 → 导出」。
- **结果分析图表**（手绘 SVG，未引入图表库）：亲和力–构象剖面、亲和力分布、
  能量漏斗、重对接 RMSD 分布；图注写明口径，并明确「预测值不等同实验结合自由能」。
- **构象排名默认折叠**，可展开。
- **分子管理界面**：按类型 / 按来源两种视图（会记住选择）、操作区按用途重排、
  分组可折叠、清空移到底部次要位置。
- **渲染与启动**：滚轮缩放合帧、hover 节流、预览 viewer 复用、抗锯齿与环境光遮蔽
  按硬件自适应（默认画质不变）；服务端启动单遍化、任务日志与构象惰性加载。
- **打包**：Linux 发布包（`.deb` / 便携 tar.gz）由 CI 从 tag 构建，版本号单一来源。

### 修复

- **页面白屏**：切换到某些页面后主内容区永久空白，必须整页重载才能恢复——根因是路由
  视图返回了多个根节点，已修复并写入开发约定。
- **作业崩溃窗口**：进程被强杀的任务不再永久停在「运行中」，历史里缺失的逐配体行可回填。
- 文件名大小写族导致的任务标签错乱；按名称取构象时把 SDF 首行的 CID 当成分子名。
- 未知位点的几何漏检有了明确说法：算法找不到时不假装找到，帮助里给出替代做法
  （用共晶配体或已知残基定盒）。

### 不包含

- Windows 发布（上游 vina 无 Windows 轮子，故仅提供 Linux 包）；MM-GBSA、GNINA
  类替代引擎、Docker 镜像等进阶项。

### Added

- **Virtual screening workbench**: import a small-molecule library (SDF / MOL / SMILES),
  dock every molecule and read a leaderboard with QED and Lipinski columns, per-row failure
  reasons, import size limits and resume after interruption.
- **Parallel batch docking**: one receptor against many ligands, with a selectable
  parallelism level, per-ligand rows and CSV export.
- **Results database**: search ligands, energies and hits across runs, persisted per workspace.
- **Interaction fingerprints (IFP) and pose clustering**: residue × interaction-type matrix
  view, plus RMSD clustering of poses.
- **Sequence view and flexible-residue picking**: inspect the receptor sequence and send
  chosen side chains straight into the docking setup.
- **Drug-likeness / ADMET-lite panel**: QED, Lipinski and descriptor summary, exportable.
- **Fetch a 3D conformer by name (PubChem)**: type a compound name, get a dockable structure.
- **Candidate binding-site detection**: cavity candidates from receptor geometry alone,
  using the alpha-sphere method from the fpocket paper; each candidate comes with a ready-to-use
  box. mmCIF receptors supported.
- **Site screen (rank candidates by docking)**: dock the same ligand into every candidate box
  and rank the boxes by best affinity, with one click to adopt the winner. This is a **coarse
  screen**: the ordering only compares these candidates, and the numbers are not comparable
  with a production docking run.
- **In-app help and glossary**: FAQ grouped by what you are trying to do, plus a glossary of
  easily misread concepts — known limitations included (for example, sites the geometric
  method cannot find).
- **Getting-started guide**: pipeline steps with status and a highlighted next step, plus a
  one-click 1iep example.
- **Methods paragraph generation**: builds a methods section from the parameters a run
  **actually used**; old runs without recorded parameters say so instead of inventing them.

### Changed

- **Docking page vs report page split**: the docking page runs and inspects, the report page
  reviews and exports; the two link to each other and the duplicated content is gone.
- **Layout and hierarchy**: the docking stage always keeps ≥62% of the width (panel 380–520 px);
  the report page is reordered as overview → poses → analysis → validation → export.
- **Analysis charts** (hand-written SVG, no chart library): affinity–pose profile, affinity
  distribution, energy funnel and redocking RMSD distribution, with captions that state the
  conventions and that a predicted value is not an experimental binding free energy.
- **Pose ranking starts collapsed** and can be expanded.
- **Molecule manager**: type/source view modes (remembered), reordered actions, collapsible
  groups, destructive clear moved to a secondary footer action.
- **Rendering and startup**: frame-coalesced zoom, throttled hover, reused preview viewers,
  hardware-adaptive anti-aliasing and ambient occlusion (default quality unchanged); single-pass
  server startup and lazy loading of logs and poses.
- **Packaging**: Linux artifacts (`.deb` and portable tarball) are built by CI from the tag,
  with a single source of truth for the version.

### Fixed

- **Blank main panel**: navigating to some pages left the content area permanently empty until a
  full reload — caused by a route view returning multiple root nodes; fixed and recorded as a
  development convention.
- **Crash window**: forcibly killed jobs no longer stay "running" forever, and missing per-ligand
  rows can be backfilled.
- Case-sensitivity family of bugs in job labels; compound names taken from an SDF whose first
  line is a CID.
- Undetected sites are now stated plainly: the geometric method does not pretend to find what it
  cannot, and the help text gives the alternative (define the box from a co-crystal ligand or known
  residues).

### Out of scope

- Windows release (upstream vina has no Windows wheels, so only Linux packages are provided);
  MM-GBSA, alternative engines such as GNINA, and Docker images.

## Historical releases

Older releases predate this file; their notes live on the release pages:

- **0.2.0** (2026-09-27) — molecule input (SMILES, the in-house 2D sketcher), docking and analysis
  (pose checks, redocking RMSD, clustering, 2D interaction diagrams, report page), persistence and
  export (job history, `.vinaproj`, self-contained HTML export), desktop and rendering work.
  [Release notes](https://github.com/hubehero/VinaStudio/releases/tag/v0.2.0)
- **0.1.0** (2026-09-23) — first public Linux release.
  [Release notes](https://github.com/hubehero/VinaStudio/releases/tag/v0.1.0)

[0.4.0]: https://github.com/hubehero/VinaStudio/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/hubehero/VinaStudio/compare/v0.2.0...v0.3.0
