# VinaStudio 学术验证报告

**简体中文** · [English](ACADEMIC_VALIDATION.md) · [主页](../README.md)

**报告版本：** 1.0  
**软件版本：** 0.6.4（开发树）  
**报告日期：** 2026-10-29  
**状态：** 可复现的软件验证报告，不是经过同行评议的基准论文。

> **一句话范围。** 本报告检验 VinaStudio 在已提交的 1IEP redocking 对照上，
> 准备、对接、位姿恢复、几何检查和报告链路是否可复现；它**不**估计通用对接
> 准确率、富集能力或结合自由能。

## 1. 范围与明确的不声明

### 1.1 本报告验证什么

- 1IEP redocking 对照，包括从 PDB HETATM 记录提取的独立晶体配体参考；
- 与上游 AutoDock Vina 教程数据的准备一致性；
- 相对该晶体参考的固定坐标系、对称性校正重原子 RMSD；
- 六项项目几何检查和盒子/参考保护；
- 固定协议下 CLI 与 Python API 对接后端的一致性；
- 验证报告记录的 provenance（来源与参数）。

### 1.2 本报告不声明什么

本报告**不**声明：

- 对未见靶点、靶点类别或化合物库的通用准确率；
- 富集、ROC、AUC、EF1%、BEDROC 或前瞻性筛选性能；
- Vina 分数等于实验结合自由能；
- 六项检查就是官方 PoseBusters 套件，或通过本检查等于通过 PoseBusters；
- 20 Å 盒子就是生物学上正确的结合位点；
- 两个 case 构成 benchmark；
- 结果可以不经重跑就跨种子、CPU 数、平台或软件版本外推。

证据范围刻意收窄。一个成功的 redocking 只是**必要对照**，不是通用准确率的
充分证据。

## 2. 研究问题与证据层级

| ID | 问题 | 主要证据 | 结论强度 |
|---|---|---|---|
| RQ1 | 配体/受体的准备是否复现文档化的上游数据？ | 字节一致性和原子数测试 | 软件一致性 |
| RQ2 | 在文档化盒子中，对接是否恢复晶体位姿？ | 固定坐标系 RMSD + 几何报告 | 单 case |
| RQ3 | 固定设置下 CLI 与 API 是否一致？ | pose 数与每 pose 能量等价测试 | 后端等价 |
| RQ4 | 保护机制是否拒绝无效盒子/参考和坏 pose？ | 单元/集成负对照 | 失败检测 |
| RQ5 | 能否根据报告复现一次运行？ | commit/版本/校验和/完整参数 | provenance |

证据优先于叙述。没有被测试、生成的报告字段或引用文献支持的陈述，都标为
限制，而不是结论。

## 3. 软件与方法

### 3.1 对接引擎

VinaStudio 0.6.4 通过 Python API 或官方命令行二进制驱动
**AutoDock Vina 1.2.7**。报告记录实际使用的后端；两者是同一个引擎，不是两种
打分方法。Vina 打分函数和搜索流程见 Trott & Olson [1]；1.2.x API 和力场变化
见 Eberhardt 等 [2]。

默认协议不表示这些参数具有普适最优性。本报告使用的值见 §5。

VinaStudio 也提供 Vinardo [14] 与 AutoDock4 [13] 打分；本报告不评估两者。

### 3.2 配体与受体准备

Meeko 负责配体参数化和 PDBQT 写入 [3]；RDKit 负责分子解析、氢处理和 ETKDG
构象生成 [4]。只有当输入、软件版本和选项都固定时，准备才是可复现的软件变换；
它不是实验测量。

1IEP 配体准备与上游教程 PDBQT 比较，比较前按文档规范化电荷列符号约定。受体
准备检查文档化的 2702 原子和元素组成。已知的 Met/Cys 硫原子类型差异被记录，
而不是隐藏。

### 3.3 RMSD 定义

位姿 RMSD 是 **重原子、对称性校正、固定坐标系** RMSD，由
`rdMolAlign.CalcRMS` 在准备好的 pose 与晶体参考之间计算。它**不**先做刚体
叠加。先叠加会把平移到其他口袋的 pose 变成人为的 ~0 Å，并破坏 redocking 的
意义。

2.0 Å 接受阈值在这里用作项目软件门槛，不是物理常数。比较性对接评估讨论了
RMSD 成功判据及其阈值敏感性 [5,6]；具体门槛仍是项目选择，并在报告中明确写出。

### 3.4 几何检查

验证器应用六项项目检查：

| 检查 | 操作定义 | 严重性 |
|---|---|---|
| `internal_clash` | 非键重原子对距离小于 0.65 × (vdW_i + vdW_j) | 拓扑距离 ≥4 的对为 error；只有可旋转 1–4 对为 warning |
| `bond_length_outlier` | pose/reference 键长差 > 0.45 Å | error |
| `angle_outlier` | pose/reference 键角差 > 25° | error |
| `planarity_break` | 芳香/双键平面 RMSD > 0.1 Å | error |
| `chirality_flip` | CIP 标签与参考不同 | error |
| `out_of_box` | 原子超出盒子边界 > 2.0 Å | error |

这些是**PoseBusters 风格子集**，受已发表检查启发 [7]，不是官方套件。阈值是
`vinastudio/core/chem/pose_validation.py` 中的项目常量，不宣称是 PoseBusters
阈值。

**氢原子处理：** `internal_clash` 只检查重原子。PDBQT 省略非极性氢，Meeko
在对接后重建氢；重建位置不能作为碰撞证据。把氢纳入曾使有效的 1IEP 重原子 pose
因 H–H 距离被拒（0.6.4 前的运行中有 3 个非最佳 pose），因此该检查只评估权威的
重原子几何。这是明确记录的工程适配，不是声称所有氢几何都不重要。

### 3.5 盒子与参考保护

盒子不含任何受体原子时，在对接前拒绝；否则 Vina 会返回一整页 0.0 kcal/mol
的结果，看起来像成功。该检查是坐标帧合理性检查，不是盒子正确性的证明。

参考必须是独立于对接配体的文件，并且通过重原子 canonical SMILES 与对接分子
匹配。无法验证的参考会使 case 失败；参考身份未知时，不会把相对 RMSD 报告为
通过。

## 4. 数据来源

### 4.1 严格 case：1IEP

| 项目 | 值 |
|---|---|
| PDB entry | 1IEP，c-Abl 激酶结构域 + 伊马替尼（STI-571）[8,9] |
| 受体输入 | `vinastudio/resources/sample/1iep/1iep_receptorH.pdb` |
| 对接配体 | `vinastudio/resources/sample/1iep/1iep_ligand.sdf` |
| 晶体参考 | `vinastudio/resources/sample/1iep/1iep_reference.sdf` |
| 晶体 HETATM 提取 | `vinastudio/resources/sample/1iep/1iep_crystal_ligand.pdb` |
| 参考来源 | RCSB 1IEP 的 `HETATM STI A 201` **坐标**，应用到教程配体的图/键级和 +1 电荷；`CONECT` 保留用于 provenance |
| 参考重原子数 | 37 |
| 配体原子数（含 H） | 69；重原子 37 |
| 参考/配体 canonical SMILES | 相同 |
| 重原子坐标最大差 | 0.000 Å |
| RCSB 1IEP 完整 PDB SHA-256 | `577386b4b8bc58a570facba0c8a843386842caef5ed7b60106c685d0f68d4218` |

上游教程 SDF 与 PDB 晶体配体的重原子坐标相同。本次改进是**坐标来源分离**：
参考坐标来自 PDB HETATM 记录，而不是把输入文件与自身比较。它仍然是同一个沉积
结构，键级、互变异构和 +1 电荷继承自教程 SDF，因此不是化学独立，也不是第二次
实验测量。报告明确这一点，避免过度表述。

验证器记录的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `1iep_receptorH.pdb` | `5f6aee6029f9a2a2c2be32d4eb948ae70808690573e1b69a0850cdffd7048ca7` |
| `1iep_ligand.sdf` | `051b8742c32adc05c07fb486a4e7c9327f84e131cee33ac4e6a568d07553eb38` |
| `1iep_reference.sdf` | `1bcc3920c107e60300fb7ac7fbe4d332c0ae2eb9b75baf2f7b7978f124343700` |
| `1iep_crystal_ligand.pdb` | `8ad50e10d641f5ad3fcdbeb2ad409d1af9850eedd95484b33f9608630cc066bd` |

### 4.2 可选 case：2HYY

2HYY [12] 是本地、gitignore 的样本，位于独立的
`validation/manifest.optional-2hyy.json`。它只作为自引用探索 case 报告，**不是**
证据，也不属于已提交核心。它的受体准备排除了 62 个模板未匹配残基，并把未解析组氨酸默认设为
HIE；这些警告与结果一起保留。带有这些警告的通过，不表示被排除残基不重要。

### 4.3 未使用的数据

本增量没有下载、分发或评估 PDBbind、CASF、DUD-E、PoseBusters 测试集或 decoy
库。CASF-2016 [10] 和 DUD-E [11] 仅用于明确缺失的 benchmark 范围。

## 5. 协议

报告生成器记录的环境：

| 项目 | 值 |
|---|---|
| 应用版本 | 0.6.4 |
| Python | 3.12.14 |
| 平台 | Linux x86_64 |
| Vina | 1.2.7 |
| Meeko | 0.8.0 |
| RDKit | 2026.9.1 |
| NumPy | 2.5.4 |
| SciPy | 1.18.1 |
| gemmi | 0.7.5 |
| 引擎后端 | `vina` Python API |
| CPU 数 | 8 |
| Git commit | 由报告记录；本草案由 dirty 工作树生成 |

1IEP 协议：

| 参数 | 值 |
|---|---|
| 盒子中心（Å） | `(15.190, 53.903, 16.917)` |
| 盒子尺寸（Å） | `(20, 20, 20)` |
| 网格间距（Å） | 0.375 |
| 打分函数 | `vina` |
| Exhaustiveness | 8（灵敏度：4 与 32） |
| 请求 pose 数 | 9 |
| Seed | 42 |
| 能量范围（kcal/mol） | 3.0 |
| 最小 RMSD（Å） | 1.0 |
| 最大评估数 | 0（Vina 启发式） |
| CPU | 0（全部可用；报告记录 8 个逻辑 CPU） |
| Refinement | 开启 |
| `allowBadResidues` | false |
| RMSD 阈值 | 2.0 Å |
| 亲和力范围 | −14.5 至 −11.0 kcal/mol |

亲和力范围是本 case 的本地接受窗口，不是公开常数。

## 6. 结果

### 6.1 1IEP redocking

命令：

```bash
uv run python scripts/validate_benchmark.py --case 1iep \
  --out-dir validation-output
```

观测结果：

| 指标 | 值 |
|---|---:|
| 状态 | passed |
| 排名第一的亲和力（kcal/mol） | −13.286 |
| 排名第一的固定坐标系 RMSD（Å） | 0.353 |
| 返回 pose 数 | 5 |
| 全部 pose 的几何 error | 0 |
| 几何 warning | 0 |
| 受体原子数 | 2702 |
| 配体原子数（PDBQT） | 40 |
| 参考匹配 | true |
| 参考独立路径 | true |

几何 error 为零是在已记录的“只检查重原子”`internal_clash` 下得到的。该适配
之前，3 个非最佳 pose 出现低于碰撞阈值的 H–H 距离；那是重建氢的伪影，不是
重原子 pose 失败。

排名第一的 pose 在不叠加的情况下相对晶体参考移动 0.353 Å。旧文档中的 0.260 Å
早于 0.6.3 从叠加式 `GetBestRMS` 改为固定坐标系 `CalcRMS`；两者不可直接比较，
本报告取代旧数字。

### 6.2 Exhaustiveness 灵敏度

固定 seed 和盒子，只改变 exhaustiveness：

| Exhaustiveness | 排名第一的亲和力（kcal/mol） | 排名第一的 RMSD（Å） | Pose 数 | Error | 观测耗时 |
|---:|---:|---:|---:|---:|---:|
| 4 | −13.286 | 0.353 | 3 | 0 | 18.3 s |
| 8 | −13.286 | 0.353 | 5 | 0 | 28.9 s |
| 32 | −13.251 | 0.360 | 6 | 0 | 173.2 s |

这是描述性灵敏度检查，不是收敛采样研究。表中耗时来自专门的灵敏度运行，不是
主报告的耗时。它说明本 case 在这三个设置下位姿恢复结论稳定；它不证明其他体系
的收敛性。

### 6.3 准备一致性

现有集成检查通过：

- 配体准备在规范化电荷符号后复现上游 PDBQT；
- 受体准备得到文档化的 2702 原子和元素计数；
- 接受的原子类型差异是 Met/Cys `S` 对上游 `SA`；逐原子电荷并非逐位相同
  （边界见下）。

这些是软件一致性检查，不是新的对接结果。受体原子类型一致，但逐原子电荷并非
逐位相同：现有测试允许平均绝对漂移低于 0.03 e、最大低于 0.75 e、430 个原子
漂移超过 0.05 e。电荷进入 Vina 打分，因此这是与打分相关的近似，不是装饰性标签。

### 6.4 CLI/API 等价

`tests/integration/test_vina_cli_backend.py` 通过 **9/9**，包括固定
seed/exhaustiveness 下相同的 pose 数和每个 pose 能量在 0.01 kcal/mol 内一致，
以及结果契约。它不比较坐标；这里说的是能量层面一致，不是逐坐标几何等价。
两个后端共享 Vina 1.2.7。

### 6.5 负对照与保护

测试覆盖：

- 完全在受体外的盒子被拒绝；
- 重原子碰撞、键长/键角异常、平面性破坏、手性翻转和出盒会产生 finding；
- 缺失的可选 case 是 `skipped`，不会计为 passed；
- 参考不匹配/无法验证时 case 失败；

这些保护支持失败检测，不证明准确率。

### 6.6 可选 2HYY

命令：

```bash
uv run python scripts/validate_benchmark.py \
  --manifest validation/manifest.optional-2hyy.json \
  --case 2hyy --out-dir validation-output
```

本地探索性运行（不属于已提交核心）：

| 指标 | 值 |
|---|---:|
| 状态 | failed（自引用，不作为证据） |
| 探索性亲和力（kcal/mol） | −12.611 |
| 自引用 RMSD（Å） | 1.117 |
| Pose 数 | 1 |
| 几何 error | 0 |
| 受体原子数 | 9673 |
| 配体原子数 | 39 |
| 警告 | 排除 62 个残基；未解析组氨酸默认 HIE |

该运行**不是**验证通过：参考就是对接配体文件本身。报告它只是为了展示自引用
case 会被拒绝。62 个残基警告保留，结果不把结论扩展到 1IEP 之外。验证器现在会记录
`independentFromLigand=false` 并让该 case 失败。

## 7. 统计处理

报告只给出描述性统计：每个 case 一个协议，主运行 5 个 pose，以及三点
exhaustiveness 灵敏度表。没有置信区间、p 值、bootstrap、秩相关、富集因子或
多重比较校正，因为设计不支持这些推断。主体系 n = 1（可选本地体系 n = 1），
加入推断统计只会制造虚假精度。

若要做定量 benchmark，正确路径是预注册、获授权、多靶点数据集，包含 held-out
体系、多种种子和明确的富集/排序终点；CASF-2016 [10] 或 DUD-E [11] 是这种范围
的例子，不是本报告的声明。

## 8. 讨论

结果支持一个很窄的结论：在已提交的 1IEP 对照上，使用文档化盒子和协议，
VinaStudio 能准备输入、对接、导出 pose，并找到一个接近晶体的位姿。它也支持
CLI 与 API 在测试协议下等价，以及已知坏输入会被拒绝而不是静默接受。

它不支持通用准确率结论。对一个激酶及其共晶配体做 redocking 是合理性检查，不是
盲测 benchmark。盒子来自已知结合位点，配体就是晶体配体，没有 decoy 或其他
靶点。审稿人应把通过视为“流程工作且对照可复现”的证据，而不是“VinaStudio
能复现任意配体”的证据。

## 9. 有效性威胁

1. **单一体系/单一靶点家族。** 1IEP 是 c-Abl + 伊马替尼；没有骨架或靶点多样性。
2. **已知位点盒子。** 盒子围绕晶体配体，不是盲搜口袋。
3. **参考来源。** 参考坐标由 PDB 提取，但与上游输入 SDF 相同；键级、互变异构
   和 +1 电荷也来自该 SDF。它是坐标来源分离，不是化学独立，也不是第二次实验测量。
4. **随机搜索。** Vina 搜索是随机的；seed 42 使本次运行可复现，不代表方法确定。
5. **每个设置一次运行。** 灵敏度表有三个 exhaustiveness 值，但没有重复种子或重复。
6. **几何检查是子集。** 不是官方 PoseBusters，也没有在带标签集合上与官方工具
   做过一致性验证。
7. **氢原子重建。** `internal_clash` 只检查重原子；C–H 和氢几何仍需审视，氢处理
   是已记录的近似。
8. **可选 2HYY 是自引用。** 其 reference 就是 ligand 文件本身，harness 会判失败；
   62 个残基被排除和 HIE 默认进一步增加限制，不能作为确认。
9. **亲和力窗口。** 接受范围是为本对照选择的，不是普适阈值。
10. **没有 benchmark 数据。** 没有运行 PDBbind/CASF/DUD-E/PoseBusters 数据集；
    无法做富集或排序声明。

## 10. 复现

```bash
# 安装并获取已提交金标准
uv sync --extra dev
uv run python scripts/fetch_samples.py
uv run python scripts/fetch_vina_cli.py   # CLI/API 等价测试需要

# 从完整 1IEP PDB 重建独立晶体参考
# （仓库已提交参考；此命令用于再生成）
uv run python scripts/build_1iep_reference.py \
  --pdb vinastudio/resources/sample/1iep/1iep.pdb \
  --ligand vinastudio/resources/sample/1iep/1iep_ligand.sdf

# 主验证报告（JSON + Markdown + per-case 工件）
uv run python scripts/validate_benchmark.py --case 1iep \
  --out-dir validation-output

# 完整测试与界面门禁
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web test
pnpm -C web build
```

生成物位于 `validation-output/`，按设计被 gitignore。JSON 报告为 schema
`2.0`，包含环境、校验和、参考独立性、完整对接参数和每个 case 的 provenance。

## 11. Claim–evidence 矩阵

| 声明 | 证据 | 结果 |
|---|---|---|
| 1IEP 配体准备在电荷规范化后与上游一致 | `tests/integration/test_ligand_prep.py` | pass |
| 1IEP 受体 2702 原子和文档化元素计数 | `tests/integration/test_receptor_prep.py`、golden test | pass |
| 排名第一的 pose 在 2 Å 内接近 PDB 坐标参考 | 生成的 `validation-report.json` | 0.353 Å |
| Pose 通过六项项目检查 | 生成的报告 | 0 error，0 warning |
| 固定协议下 CLI 与 API 一致 | `tests/integration/test_vina_cli_backend.py` | 9/9 pass |
| 无效盒子被拒绝 | `tests/unit/test_box.py`、`tests/integration/test_docking_api.py` | pass |
| 缺失可选 case 是 skipped，不是 passed | `tests/unit/test_validation.py` | pass |
| 参考图与对接配体一致 | harness provenance + `reference_matches_poses` | true（两者都源自教程 SDF） |
| 不声明富集/通用准确率 | 本报告 + 未运行数据集 | 显式不声明 |

## 12. 参考文献

逐条 claim→来源追踪见 [`docs/references/VALIDATION_CLAIMS.md`](references/VALIDATION_CLAIMS.md)。

元数据于 2026-10-29 组装并对照 Crossref 核对；PDB entry 通过 RCSB 核对。完整
BibTeX：[`docs/references/VinaStudio.bib`](references/VinaStudio.bib)。访问与
许可说明：[`docs/references/README.md`](references/README.md)。全文通过 DOI/
出版社链接获取；仓库只附许可允许再分发的开放获取 PDF。

1. **Trott, O.; Olson, A. J.** AutoDock Vina: Improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading. *Journal of Computational Chemistry* **2010**, 31(2), 455–461. doi:[10.1002/jcc.21334](https://doi.org/10.1002/jcc.21334).
2. **Eberhardt, J.; Santos-Martins, D.; Tillack, A. F.; Forli, S.** AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, and Python Bindings. *Journal of Chemical Information and Modeling* **2021**, 61(8), 3891–3898. doi:[10.1021/acs.jcim.1c00203](https://doi.org/10.1021/acs.jcim.1c00203).
3. **Santos-Martins, D.; He, Y.; Eberhardt, J.; Sharma, P.; Bruciaferri, N.; Holcomb, M.; Llanos, M. A.; Hansel-Harris, A.; Barkdull, A. P.; Tillack, A. F.; Bianco, G.; Paulsen, M.-L.; Mato, J.; Taneja, I.; Forli, S.** Meeko: Molecule Parametrization and Software Interoperability for Docking and Beyond. *Journal of Chemical Information and Modeling* **2025**, 65(24), 13045–13050. doi:[10.1021/acs.jcim.5c02271](https://doi.org/10.1021/acs.jcim.5c02271).
4. **Riniker, S.; Landrum, G. A.** Better Informed Distance Geometry: Using What We Know To Improve Conformation Generation. *Journal of Chemical Information and Modeling* **2015**, 55(12), 2562–2574. doi:[10.1021/acs.jcim.5b00654](https://doi.org/10.1021/acs.jcim.5b00654).
5. **Bissantz, C.; Folkers, G.; Rognan, D.** Protein-Based Virtual Screening of Chemical Databases. 1. Evaluation of Different Docking/Scoring Combinations. *Journal of Medicinal Chemistry* **2000**, 43(25), 4759–4767. doi:[10.1021/jm001044l](https://doi.org/10.1021/jm001044l).
6. **Kellenberger, E.; Rodrigo, J.; Muller, P.; Rognan, D.** Comparative evaluation of eight docking tools for docking and virtual screening accuracy. *Proteins: Structure, Function, and Bioinformatics* **2004**, 57(2), 225–242. doi:[10.1002/prot.20149](https://doi.org/10.1002/prot.20149).
7. **Buttenschoen, M.; Morris, G. M.; Deane, C. M.** PoseBusters: AI-based docking methods fail to generate physically valid poses or generalise to novel sequences. *Chemical Science* **2024**, 15(9), 3130–3139. doi:[10.1039/D3SC04185A](https://doi.org/10.1039/D3SC04185A). 开放获取，CC BY。
8. **Nagar, B.; Bornmann, W. G.; Pellicena, P.; Schindler, T.; Veach, D. R.; Miller, W. T.; Clarkson, B.; Kuriyan, J.** Crystal structures of the kinase domain of c-Abl in complex with the small molecule inhibitors PD173955 and imatinib (STI-571). *Cancer Research* **2002**, 62(15), 4236–4243. PMID: [12154025](https://pubmed.ncbi.nlm.nih.gov/12154025/).
9. **RCSB Protein Data Bank.** 1IEP: c-Abl kinase domain in complex with imatinib (STI-571). doi:[10.2210/pdb1IEP/pdb](https://doi.org/10.2210/pdb1IEP/pdb); [结构页](https://www.rcsb.org/structure/1IEP)。
10. **Su, M.; Yang, Q.; Du, Y.; Feng, G.; Liu, Z.; Li, Y.; Wang, R.** Comparative Assessment of Scoring Functions: The CASF-2016 Update. *Journal of Chemical Information and Modeling* **2019**, 59(2), 895–913. doi:[10.1021/acs.jcim.8b00545](https://doi.org/10.1021/acs.jcim.8b00545)。本报告未使用，仅用于说明 benchmark 范围。

11. **Mysinger, M. M.; Carchia, M.; Irwin, J. J.; Shoichet, B. K.** Directory of Useful Decoys, Enhanced (DUD-E): Better Ligands and Decoys for Better Benchmarking. *Journal of Medicinal Chemistry* **2012**, 55(14), 6582–6594. doi:[10.1021/jm300687e](https://doi.org/10.1021/jm300687e)。本报告未使用，仅用于说明未来富集评估范围。
12. **RCSB Protein Data Bank.** 2HYY: c-Abl kinase domain in complex with imatinib. doi:[10.2210/pdb2HYY/pdb](https://doi.org/10.2210/pdb2HYY/pdb); [结构页](https://www.rcsb.org/structure/2HYY)。可选本地输入，不属于已提交核心证据。

13. **Morris, G. M.; Huey, R.; Lindstrom, W.; Sanner, M. F.; Belew, R. K.; Goodsell, D. S.; Olson, A. J.** AutoDock4 and AutoDockTools4: Automated docking with selective receptor flexibility. *Journal of Computational Chemistry* **2009**, 30(16), 2785–2791. doi:[10.1002/jcc.21256](https://doi.org/10.1002/jcc.21256)。本报告未评估。
14. **Quiroga, R.; Villarreal, M. A.** Vinardo: A Scoring Function Based on AutoDock Vina Improves Scoring, Docking, and Virtual Screening. *PLOS ONE* **2016**, 11(5), e0155183. doi:[10.1371/journal.pone.0155183](https://doi.org/10.1371/journal.pone.0155183)。开放获取，CC BY 4.0；本报告未评估。

## 13. 报告历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-10-29 | 初始 0.6.4 报告；独立 1IEP 参考；provenance schema；重原子碰撞检查。 |
