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

## [0.6.1] - 2026-10-26

### 新增

- **本地库选择器**：批量筛选与虚拟筛选共用 Catalog Picker，支持 Study/集合/
  筛选库/未归类 scope、名称与标签检索、MW/QED/Lipinski/TPSA/LogP/可旋转键
  过滤、仅已准备、分页和全选匹配；可把结果保存为筛选库。
- **大规模运行选择**：大结果由服务端冻结为运行选择，批量/虚拟筛选只传
  selection id；源文件按需读取，未准备配体在运行前惰性准备，不再复制整库。
- **Catalog 描述符索引**：导入时保存描述符并建立索引，支持大库筛选；
  选择器在 5k/50k 规模下完成分页与全选验证。

### Added

- **Local library picker**: Batch and Screening share a Catalog picker with
  Study/Collection/Library scopes, name/tag search, MW/QED/Lipinski/TPSA/LogP/
  rotatable-bond filters, prepared-only mode, paging and select-all-matching;
  a result can be saved as a screening library.
- **Large run selections**: the server freezes large results into a run
  selection; Batch/Screening send only its id. Source structures are read
  directly and missing ligands are prepared lazily instead of copying the whole
  library.
- **Catalog descriptor indexes**: descriptors are stored and indexed at import
  for large-library filtering; the picker was exercised at 5k/50k scale.

### 修复

- **依赖安全更新**：setuptools 升级到 84.2.1，修复 Windows legacy wheel
  安装路径可能写出目标目录的问题。

### Fixed

- **Dependency security update**: setuptools is updated to 84.2.1, fixing a
  Windows legacy-wheel install path escape.

## [0.6.0] - 2026-10-25

### 新增

- **分子目录 Catalog**：工作区级 SQLite 分子目录，按 InChIKey/PDB ID 身份去重，
  支持 Study（多受体/配体）、可嵌套集合、标签与筛选库；旧 `molecules.json`
  与 `libraries/` 自动迁移并保留备份。
- **服务端检索与智能建议**：FTS5 文本检索、字段过滤、分页与解释型分类建议
  （Study 配对、角色、重复、准备）；前端不再全量过滤。
- **Catalog 筛选库**：可从选中分子/集合/检索结果创建库，接入现有筛选
  管线；批量筛选与虚拟筛选可复用。
- **Catalog 导入与管理闭环**：文件、SMILES、2D 画板、内置示例、RCSB、
  PubChem、ChEMBL/化合物库统一写入 Catalog；支持保存检索、来源/标签/状态
  facet、排序、页大小、全选筛选结果、批量标签、Study/集合/筛选库管理。
- **大列表浏览**：Catalog 表格改用行虚拟渲染，并支持持久化列显示配置；
  服务器仍按页返回，后续页通过分页访问。
- **筛选结果追溯**：运行和历史显示 Catalog Library 的显示名；排名行可打开
  单配体详情（评分、构象数、QED/Lipinski、SMILES、耗时、输出目录）。

### 修复

- **化合物下载路径显式约束**：在线库下载写入前再次经 `resolve_within` 限定在工作区，
  恶意/异常 provider ID 不能把文件写出目标目录。

### Added

- **Molecule Catalog**: a workspace-level SQLite catalog keyed by InChIKey/PDB
  identity, with Studies (multiple receptors/ligands), nested collections, tags
  and screening libraries; the legacy `molecules.json` and `libraries/` data
  migrate once with a backup.
- **Server-side search and suggestions**: FTS5 search, field filters, paging and
  explainable suggestions for Studies, roles, duplicates and preparation.
- **Catalog screening libraries**: create a library from selected molecules, a
  collection or the current search and run it through the existing screening
  pipeline for batch and virtual screening.
- **One import path for the Catalog**: files, SMILES, the 2D sketcher, bundled
  samples, RCSB, PubChem and ChEMBL/compound libraries all write to the Catalog;
  saved searches, source/tag/status facets, sorting, page size, select-all,
  bulk tags and Study/collection/library management are available.
- **Large-list browsing**: the Catalog table renders rows virtually and
  remembers visible columns; the server still serves bounded pages.
- **Screening traceability**: runs and history show the Catalog library display
  name, and a ranking row opens per-ligand scores, SMILES, elapsed time and the
  output directory.

### Fixed

- **Compound downloads are explicitly contained**: the write target is resolved
  inside the workspace before use, so an abnormal provider id cannot escape the
  ligands directory.

## [0.5.1] - 2026-10-24

### 新增

- **化合物库检索扩展**：分子库新增 PubChem/ChEMBL 化合物检索，支持名称/ID、
  相似性与子结构模式、分页、来源与许可提示；ChEMBL 的 2D 结构会明确提示
  先准备生成 3D；RCSB 结果支持“加载更多”。原有 RCSB 与 PubChem 快捷获取
  入口继续保留。

### 修复

- **盒子与受体不匹配时不再伪造成功结果**：对接前检查盒子是否包含受体原子；
  盒子完全落在受体外（例如用 3htb 受体配 1iep 盒子）会报错并提示核对受体与
  盒子，而不是生成一页 0.0 kcal/mol 的“完成”结果。
- **工程保存更可靠**：`Ctrl+S` 覆盖当前 `.vinaproj`，不再每次生成 `_1`
  副本；另存为使用原生文件对话框选择路径和名称，默认进入工作区
  `projects/`；工程文件采用原子写入，并校验 `.vinaproj` 扩展名。
- **对接进度不再“假动画”**：Vina 1.2.7 不提供可靠实时百分比；单任务运行
  改为阶段/活动条（算地图→搜索→导出），批量/筛选仍显示真实完成计数。
  解析器同时支持一行多个百分比，不再只取第一个 0%。
- **结果表的非负/零亲和力有明确警示**：历史任务与结果汇报不再把
  `0.00` 或正值仅显示为绿色“已完成”；0.00 提示检查受体/盒子与日志，
  正值说明计算完成但没有预测到有利结合。
- **工程加载不再重复分子**：工程保存的是准备后的 PDBQT；加载时按源文件
  或任一产物路径复用，必要时先检查 PDBQT 再接入对接管线，不再多出一份
  “已上传”副本，也不会把 PDBQT 误标成 SDF。
- **浏览器模式“另存为”不再静默失败**：没有原生文件对话框时下载
  `.vinaproj`，并明确提示自定义目录需桌面版。
- **奇数体素盒子可修复**：盒子页新增“强制偶数体素”开关，已知英文告警
  改为中文；开启后写亲和力图检查变为可写。
- **历史检索与历史任务表修正**：有结果时不再同时显示“暂无结果”；批量
  结果使用配体名/批量筛选标签，不再显示空白；窄窗口下配体列不再竖排，
  hover 可看完整名称。

### Added

- **Compound library search**: the molecule library now searches PubChem and
  ChEMBL by name/ID, similarity and substructure, with paging, source/licence
  labels and explicit 2D-to-prepare warnings for ChEMBL. RCSB results gain
  Load more; the existing RCSB and PubChem quick-fetch paths remain available.

### Fixed

- **A box outside the receptor is no longer reported as success**: docking now
  checks that the search box contains receptor atoms. A box entirely outside the
  receptor (for example, a 3htb receptor with a 1iep box) is rejected with an
  actionable error instead of producing a page of 0.0 kcal/mol "completed"
  poses.
- **Project saving is reliable**: Ctrl+S overwrites the current `.vinaproj`
  instead of creating a `_1` copy; Save As uses the native file dialog for path
  and name, starting in the workspace `projects/` folder; project files are
  written atomically and must use the `.vinaproj` extension.
- **Docking progress no longer fakes percentages**: Vina 1.2.7 exposes stages,
  not reliable live percentages. Single jobs now show a stage/activity bar
  (maps → search → export); batch/screening keep real completed counts. The
  parser also expands every percentage on a Vina line instead of only the first
  `0%`.
- **Non-negative affinity is flagged**: history and the result report no longer
  present `0.00` or positive scores as an unqualified green success. `0.00`
  points to the receptor/box and log; a positive score means the calculation
  completed but predicts no favourable binding.
- **Project loading no longer duplicates molecules**: projects store the
  prepared PDBQT path; loading now reuses an existing source or artifact and
  inspects a stored PDBQT before reconnecting it to the pipeline. The ligand
  label also follows the actual format instead of claiming SDF for PDBQT.
- **Browser Save As no longer fails silently**: without a native dialog it
  downloads the `.vinaproj` and says that a custom directory needs the desktop
  app.
- **Odd-voxel boxes are recoverable**: the box panel has a “Force even voxels”
  switch, and the known English warning is localized.
- **History fixes**: results search no longer shows “No results” alongside
  rows; batch runs get a ligand/batch label; the narrow history table no longer
  stacks the ligand header, and a tooltip exposes the full name.
- **Web API docs**: Vite proxies `/docs` and `/swagger`, so the settings link
  reaches Swagger instead of returning the SPA.

## [0.5.0] - 2026-10-23

### 新增

- **设置 → 通用 → 检查更新**：手动检查 GitHub Releases；有新版本时打开官方
  释放页面，不下载、不安装。
- **导入结果包**：报告页可导入 VinaStudio 导出的 zip，作为新的只读结果打开，
  可查看构象、参数与日志；不覆盖当前项目。
- **结果包保存位置**：导出结果包写入工作区 `exports/result-bundles/`，文件名带
  时间与 jobId；每次导出新增文件，成功提示显示绝对路径。
- **出版图形导出**：3D 视口支持 1×/2×/3× PNG；2D 相互作用图可单独导出 SVG。
- **构象叠合**：结果页可叠合前 20 个构象，颜色只区分姿态，不代表能量。
- **可复制图注**：报告页生成含参数/口径的图注，明确预测性质与“未绘制静电势”。
- **结果整理**：历史检索支持收藏、标签、批量打标和保存筛选视图；索引自动升级，
  重建索引不会清掉标签/收藏。检索每页 50 条，可「加载更多」继续查看更早结果。
- **命令面板与撤销**：Ctrl/Cmd+K 打开命令面板，Ctrl/Cmd+Z 撤销上一步危险操作
  （删除分子/清空列表/删除保存视图），`?` 查看快捷键；删除前会确认。
- **帮助知识库**：帮助页可搜索，并支持从准备失败、候选位点、AD4 地图、任务失败
  和软件渲染警告直接跳到对应条目；新增结果包、Windows SmartScreen/抗锯齿、
  更新检查等中英说明。
- **可复现验证基线**：新增 `validation/manifest.json` 与
  `scripts/validate_benchmark.py`，对 1iep/2hyy 执行 redocking 并输出
  JSON/Markdown；缺失数据明确 skip，几何检查是 PoseBusters 风格子集。
- **准备报告 2.0**：可保留指定水/金属；报告逐项列出删除/保留、组氨酸
  HID/HIE/HIP 状态、altloc 策略、模板排除与未建模假设；单次对接的
  job.json/Methods 会写入准备摘要，并明确质子化/电荷来源与缺失原子未重建。
- **相互作用 2.0**：新增卤键（距离候选）、金属配位与水介导；支持按残基
  汇总和 CSV 导出。离子作用标为盐桥候选；卤键未做角度；金属/水需在准备
  时保留；仍不含 π-堆积。
- **Ensemble 多构象对接**：同一配体可分别对多个已准备受体构象对接，逐构象
  列出最佳亲和力并标记 best；共用盒子，不是 induced fit/IFD；单受体路径不变。

### Added

- **Settings → General → Check for updates**: manually checks GitHub Releases
  and opens the official release page when a newer version exists, without
  downloading or installing anything.
- **Import result bundle**: the report page opens a zip exported by VinaStudio
  as a new read-only result with its poses, parameters and log; the current
  project is never overwritten.
- **Result bundle location**: exports are written to the workspace's
  `exports/result-bundles/` folder with a timestamped name; each export adds a
  new file and the success message shows the absolute path.
- **Publication figures**: the 3D viewport exports 1×/2×/3× PNG, and the 2D
  interaction diagram exports as a standalone SVG.
- **Pose overlay**: the result card overlays the first 20 poses; colours identify
  poses only, not affinity.
- **Copyable figure caption**: the report page generates a caption with the run
  parameters and an explicit prediction/no-electrostatic-potential caveat.
- **Result organisation**: results search supports favourites, tags, bulk tagging
  and saved filter views; the index upgrades automatically and re-indexing keeps
  tags and favourites. Results load 50 at a time with a Load more button.
- **Command palette and undo**: Ctrl/Cmd+K opens the command palette, Ctrl/Cmd+Z
  undoes the last destructive action (delete molecule, clear list, delete saved
  view), and `?` shows the shortcut overview; deletions ask for confirmation.
- **Help knowledge base**: help is searchable, and preparation failures, candidate
  sites, AD4 maps, failed jobs and the software-renderer warning link straight to
  the matching entry; new bilingual notes cover result bundles, Windows
  SmartScreen/antialiasing and update checks.
- **Reproducible validation baseline**: `validation/manifest.json` and
  `scripts/validate_benchmark.py` run redocking for the committed 1iep case and
  the optional 2hyy sample, writing JSON/Markdown reports; missing data is
  explicitly skipped and the geometry checks are a PoseBusters-style subset.
- **Preparation report 2.0**: keep selected waters/metals; the report lists
  deleted/kept groups, HID/HIE/HIP histidine states, the altloc policy,
  template-excluded residues and unmodelled assumptions. Single-run job.json and
  Methods carry the preparation summary and state the protonation/charge source
  and that missing atoms were not rebuilt.
- **Interaction analysis 2.0**: adds halogen bonds (distance candidates), metal
  coordination and water-mediated contacts, plus a per-residue summary and CSV
  export. Ionic contacts are labelled salt-bridge candidates; halogen bonds have
  no angle test; metals/waters must be retained during preparation; π-stacking
  remains absent.
- **Ensemble docking**: one ligand can be docked against several prepared
  receptor conformers, with per-conformer best affinity and a best marker. The
  box is shared and this is not induced fit/IFD; the single-receptor path is
  unchanged.

## [0.4.1] - 2026-10-21

依赖安全更新。功能与 0.4.0 相同；建议 0.4.0 用户升级。

### 安全

- 更新 `certifi` 到 2026.10.19，修复其根证书包中的 CA 问题。
- 更新 `Pillow` 到 13.0.0，修复图像解码与编码路径上的多个高危问题
  （堆越界、未初始化内存、递归与拒绝服务等）。
- 更新 `Vite` 到 8.3.4（仅开发与构建期使用），修复 `launch-editor` 的高危问题。

### Security

- Updated `certifi` to 2026.10.19 for the root-certificate bundle advisory.
- Updated `Pillow` to 13.0.0 for multiple high-severity image decoding and
  encoding issues (heap overflows, uninitialised memory, recursion and denial of
  service).
- Updated `Vite` to 8.3.4 (development and build only) for the `launch-editor`
  advisory.

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

[0.5.1]: https://github.com/hubehero/VinaStudio/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/hubehero/VinaStudio/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/hubehero/VinaStudio/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/hubehero/VinaStudio/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/hubehero/VinaStudio/compare/v0.2.0...v0.3.0
