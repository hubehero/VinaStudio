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

## [0.6.5] - 2026-10-30

### 新增

- **可复现功能验证记录**：新增 `validation/functional/`，包含功能矩阵、环境与输入哈希、全量测试 JUnit、生产界面路由冒烟、用户流程截图和原始结果；协议、证据等级与未覆盖项在记录中明确列出。
- **诊断与安全修复**：环境自检新增只读诊断，检查工作空间、目录、目录数据库、任务索引、对接引擎、科学计算依赖、磁盘空间和浏览器渲染器；可安全重建的目录问题可一键修复，其余问题保留原因、证据和修改建议。自动修复不会删除或覆盖分子、构象、工程、任务索引或数据库。

### 修复

- **历史结果隔离**：结果汇报中的历史任务不再被工作台当成当前管线结果；切换受体或配体仍会清除旧结果，历史任务仍可在对接页检视。
- **历史相互作用**：相互作用分析优先使用任务记录的受体，避免换过当前分子后把旧 pose 与另一受体组合。
- **窄屏 Catalog**：窄窗口下选中分子的详情、预览和准备入口改为底部整行保留，不再消失。
- **软件渲染**：显式软件渲染模式使用 ANGLE SwiftShader 创建 WebGL 上下文，嵌入界面的 3D 视口不再因空上下文启动失败。
- **筛选进度**：历史取消任务的越界进度值在界面夹紧为 0–100%，不修改原始历史记录。
- **地图错误边界**：奇数量体且未启用 `forceEvenVoxels` 的亲和力图请求返回可解释的 422，而不是泄露 Vina 的 500。

### Added

- **Reproducible functional validation record**: add `validation/functional/` with a feature matrix, environment and input hashes, full test JUnit, production UI route smoke, user-flow screenshots and raw results; the protocol, evidence levels and unverified items are explicit.
- **Diagnostics and safe repair**: the environment check now runs read-only checks for the workspace, directories, catalog database, job indexes, docking engine, scientific dependencies, disk space and browser renderer. Safe directory findings can be repaired in one action; other findings retain the reason, evidence and recommended action. Repair never deletes or overwrites molecules, poses, projects, job indexes or databases.

### Fixed

- **Historical result isolation**: a result loaded from the report/history view is no longer presented by the workbench as the current pipeline result; changing receptor or ligand still clears stale results, while history remains inspectable in the docking view.
- **Historical interaction analysis**: contacts now use the receptor recorded by the job, instead of combining an old pose with a different current receptor.
- **Narrow Catalog layout**: the selected molecule's detail, preview and preparation entry remain available as a full-width bottom row at narrow widths.
- **Software rendering**: the explicit software-render mode asks ANGLE for SwiftShader, so the embedded 3D viewport no longer fails to create a WebGL context.
- **Screening progress**: out-of-range progress from a historical cancelled run is clamped to 0–100 in the interface without rewriting the stored record.
- **Map error boundary**: an affinity-map request with odd voxels and `forceEvenVoxels` disabled returns an actionable 422 instead of leaking a Vina 500.

## [0.6.4] - 2026-10-29

### 新增

- **学术验证报告**：新增中英双语 `docs/ACADEMIC_VALIDATION`，包含独立 1IEP PDB 晶体参考、claim–evidence 矩阵、复现命令和 14 条经 DOI 核对的参考文献；验证器记录版本、提交、后端、输入校验和与完整对接参数。报告明确只验证 1IEP 对照，不声明多靶点准确率、富集或 PoseBusters 通过率。

- **Catalog 工作台布局**：标题/主操作/工具带分层，低频操作收进 More，来源/状态/标签筛选进入 Filters 面板；搜索、排序、分页和响应式断点同步整理。
- **Dock 工作台布局**：右栏改为“参数 / 分析 / 结果”Inspector 标签页，结果工具条收敛并把聚类收进可展开面板；切换受体或配体时自动清除上一分子的旧结果、pose 和相互作用。

### Added

- **Academic validation report**: add bilingual `docs/ACADEMIC_VALIDATION`, an independent 1IEP PDB crystal reference, a claim–evidence matrix, reproduction commands and 14 DOI-checked references; the harness records versions, commit, backend, input checksums and full docking parameters. The report is explicitly limited to the 1IEP control and claims no multi-target accuracy, enrichment or PoseBusters pass rate.

- **Catalog workbench layout**: title, primary actions and tool strip are separated; low-frequency actions move into More, source/status/tag facets into Filters, with responsive breakpoints and a calmer table-first layout.
- **Dock workbench layout**: the inspector is now Parameters / Analysis / Results; result actions are compact and clustering is collapsible; switching receptor or ligand clears the previous molecule's poses, results and interactions automatically.

### 修复

- **自定义打分权重**：Python API 后端现在在 affinity map 生成前设置权重；权重长度/有限性在 API schema 校验，权重与预计算 maps 的组合会被明确拒绝；交互 `/score`、`/optimize`、`/randomize` 接受同一组权重。
- **盒体与资源边界**：所有盒体尺寸在 schema 层要求有限正数；spawned 对接作业也受地图网格预算约束，不再只有交互端点拒绝超大盒子。
- **架构边界**：`core.paths` 不再 import FastAPI/server；活动工作区由 server 注入 provider，engine-only 导入保持可用。
- **发布镜像开发入口**：发布树补齐 `web_start.sh`，并移除指向不存在 `tests/` 的 pytest 配置。
- **第三方许可**：新增 `THIRD_PARTY_LICENSES.md` 与 LGPL/Apache/BSD 许可证文本，安装包和 Debian 包引用。

### Fixed

- **Custom scoring weights**: the Python API backend now sets weights before affinity-map generation; length/finite validation is in the API schema, weights plus precomputed maps are rejected, and `/score`, `/optimize`, `/randomize` accept the same weight vector.
- **Box and resource limits**: all box dimensions must be finite and positive at the schema boundary; spawned docking jobs share the map-cell budget instead of only interactive endpoints rejecting oversized boxes.
- **Architecture boundary**: `core.paths` no longer imports FastAPI/server; the server injects the active-workspace provider so engine-only imports remain valid.
- **Release-tree development entry**: `web_start.sh` is present in the release tree and the release pytest config no longer points at a missing `tests/` directory.
- **Third-party licensing**: added `THIRD_PARTY_LICENSES.md` plus LGPL/Apache/BSD texts, referenced by the Windows installer and Debian copyright.

## [0.6.3] - 2026-10-29

### 修复

- **Redocking RMSD**：配体与晶体参考比较时不再做刚体叠加；错位到其他口袋的 pose 不再被报成 0 Å，聚类也不会合并不同结合位点。
- **Catalog 筛选**：QED/TPSA/LogP/HBD/HBA/可旋转键筛选现在真正参与检索和“全选匹配”，不再冻结未过滤的分子集合。
- **对接失败与复现**：对接/批量失败会显示错误；seed、exhaustiveness、权重、地图前缀等参数在页面切换和工程保存/恢复后保留。
- **受体准备**：无 HD1/HE2 的组氨酸明确记录为 HIE 默认假设；批量/虚拟筛选拒绝缺少地图通道的 AD4。
- **Catalog 交互**：切换筛选器会刷新结果；支持编辑分子别名；空结果有明确提示；工程删除需要确认；未连接后端时不再显示首次工作区向导。

- **运行快照失效**：删除选择成员会把批量/筛选选择标记为 stale，运行前拒绝并提示重建；库成员/准备产物变化会失效旧的 legacy 物化目录。
- **交互打分边界**：`/score`、`/optimize`、`/randomize` 共用单飞地图构建并限制盒体网格数，超限返回可解释的 4xx。
- **验证与 API 边界**：参考结构无法匹配或任一人为 pose 几何错误会阻止验证通过；Catalog 常见非法成员/重复入口返回 4xx；上传使用原子独占创建。
- **Redocking 控制台**：结果页显示 top/best pose 的固定坐标系 RMSD、成功率与判定，并提供本次运行协议摘要和复制。
- **内置药物图形**：内置库的 2D 源改用 CoordGen、环模板和规范朝向，并写入立体楔形/虚键；详情预览新增 `/preview3d`，对 2D 源用 ETKDG 生成缓存的 3D 构象，不再只显示平面骨架。旧工作区会一次性刷新仍属于内置库的 2D SDF，不重建已删除的库。

### Fixed

- **Redocking RMSD**: ligand-to-reference comparison no longer rigid-body superposes; a pose moved to another pocket is no longer reported as 0 Å, and clustering does not merge different sites.
- **Catalog filters**: QED/TPSA/LogP/HBD/HBA/rotatable filters now affect both results and “select all matching” instead of freezing an unfiltered set.
- **Failure and reproducibility**: docking/batch failures show their error; seed, exhaustiveness, weights and map prefix survive navigation and project save/load.
- **Receptor preparation**: histidines without HD1/HE2 are explicitly reported as a HIE default; batch/screening reject AD4 without a map channel.
- **Catalog UX**: changing filters refreshes results; aliases are editable; empty results are explained; project deletion confirms; an unreachable backend no longer opens the first-launch wizard.

- **Run snapshot invalidation**: deleting a selection member marks affected batch/screening selections stale and blocks the run with a rebuild prompt; library membership/preparation changes invalidate the old legacy materialisation.
- **Interactive scoring bounds**: `/score`, `/optimize` and `/randomize` share one map-building slot and reject boxes above the grid-cell limit with an explanatory 4xx.
- **Validation/API boundaries**: an unmatched reference or any pose with a geometry error now prevents a validation pass; common malformed Catalog members/duplicate entries return 4xx; uploads use exclusive atomic creation.
- **Redocking console**: the results view shows fixed-frame top/best pose RMSD, success and verdict, plus a copyable run-protocol summary.
- **Built-in depictions**: built-in 2D sources now use CoordGen ring templates and canonical orientation, with wedge/hash stereo bonds, while the detail viewer uses a cached ETKDG `/preview3d` conformer instead of showing only the flat skeleton. Existing workspaces refresh owned built-in SDFs once without recreating a deleted library.

## [0.6.2] - 2026-10-27

### 新增

- **内置本科药物库**：内置 125 个本科药理学/药物化学常用药物，带中文通用名、
  类别与来源信息；首次打开工作区时播种，可编辑或删除。
- **内置本科受体库**：内置 27 个 RCSB PDB 药物靶点结构，按靶点类别放入嵌套
  集合；详情显示 PDB ID、物种、链、共晶配体、方法、分辨率和构建体备注。
- **Catalog 展示**：名称显示英文与中文通用名；表格精简为名称/类型/准备/
  分子量/标签，Study、来源和集合移到右侧详情；受体显示由建模蛋白残基计算
  的蛋白分子量，并标注不包含配体、水和缺失残基。
- **受体准备默认值**：新增“默认允许模板匹配失败的残基”设置，默认开启；
  设置作用于新准备会话与新分子，单个分子仍可在准备对话框中单独开关。
  被模板排除的残基继续写入准备报告。

### Added

- **Built-in undergraduate drug library**: 125 teaching drugs with Chinese
  generic names, classes and provenance, seeded on first workspace access and
  editable or removable.
- **Built-in undergraduate receptor collection**: 27 RCSB PDB drug-target
  structures grouped by target class; details show PDB ID, organism, chains,
  co-crystal ligand, method, resolution and construct note.
- **Catalog presentation**: English and Chinese names are shown together; the
  table keeps name/type/preparation/MW/tags while Study, source and collections
  move to the detail panel. Receptors show the protein mass calculated from
  modelled residues, explicitly excluding ligands, waters and missing residues.
- **Receptor preparation default**: a new “Allow residues that fail template
  matching by default” setting, on by default. It applies to new preparation
  sessions and molecules; each preparation can still override it, and ignored
  residues stay in the report.

### 修复

- **受体详情**：无共晶配体的结构显示“无（apo）”，不再把内部标记 `none`
  直接展示给用户。
- **Catalog 列设置**：旧版保存的 Study/来源/集合列会迁移到新的五列布局，
  避免窄窗口下互相覆盖。

### Fixed

- **Receptor details**: apo structures now show “None (apo)” instead of the raw
  internal `none` marker.
- **Catalog column settings**: saved Study/source/collection columns migrate to
  the five-column layout, avoiding overlap in narrow windows.

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
