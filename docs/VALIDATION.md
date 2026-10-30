# VinaStudio 验证基线（2026-10-29）

本文说明 `scripts/validate_benchmark.py` 能证明什么、不能证明什么，以及如何
扩展数据集。它是**redocking 验证 harness**，不是精度排行榜。完整的学术报告、
参考文献和 claim–evidence 矩阵见
[ACADEMIC_VALIDATION.zh-CN.md](ACADEMIC_VALIDATION.zh-CN.md)。

> **一句话**：用固定数据/版本/种子跑通准备→对接→RMSD→几何检查，把结果、
> 警告、失败和跳过都写出来；`passed` 只代表该 case 的排名第一 pose 满足本文件
> 的条件、且所有 pose 没有几何 error，不代表 VinaStudio 在所有靶点上准确。

## 1. 快速开始

```bash
uv run python scripts/validate_benchmark.py --list
uv run python scripts/validate_benchmark.py --case 1iep
# optional local negative control (not part of default evidence)
uv run python scripts/validate_benchmark.py --manifest validation/manifest.optional-2hyy.json --case 2hyy --out-dir validation-output
```

输出：

- `validation-output/validation-report.json`（报告 schema 2.0，含 provenance）
- `validation-output/validation-report.md`
- `validation-output/cases/<id>/`：配体/受体 PDBQT、dock 输出、SDF 等工件

退出码：有 `failed` → 1；只有 `skipped` → 0；`--strict` 时 `skipped` 也返回 1。
`--exhaustiveness` 可覆盖 manifest 的穷举度，用于灵敏度/成本对照。

## 2. 默认 cases

| ID | 体系 | 数据 | 默认？ |
|---|---|---|---|
| `1iep` | c-Abl 激酶 + 伊马替尼 | `vinastudio/resources/sample/1iep/`（已提交，独立晶体参考） | 是 |
| `2hyy` | c-Abl 激酶 + 伊马替尼（高分辨率） | `sample/`（本地下载，gitignore） | 否；独立 optional manifest，自引用负对照 |

`sample/` 里的 1hsg/3htb/3eml 文件是**格式/读写样例**，其配体参考没有被本
基线验证为 co-crystal redocking 真值（1hsg 的 sample 配体分子式与 PDB 配体
不符），因此不在默认 manifest 中；不要为了“多体系”把它们硬算成通过。

## 3. 通过条件

一个 case 只有在以下全部满足时为 `passed`：

1. docking 至少产生 1 个 pose；
2. 排名第一（Vina model 1）的 pose 相对参考配体的 heavy-atom RMSD ≤
   `rmsdThreshold`（默认 2.0 Å，项目门槛，不是物理常数）；
3. **任意** pose 的六项几何检查都没有 `error`；
4. 参考必须是独立文件，且与对接配体的 canonical SMILES 一致；
5. 若 manifest 配置了 `affinityRange`，排名第一的 affinity 在区间内。

在进入上述判定之前还有一条**对接前置条件**：盒子必须包含至少一个受体原子
（`ensure_box_contains_receptor`）。盒子完全在受体外时，Vina 会返回全 0.0
的构象并把它当成完成；现在 harness 和实际作业都会直接报错，不会把这种结果
计入 passed。该检查只证明“盒子与受体有交集”，**不证明盒子是正确结合位点**；
位点正确性仍要靠共晶配体/RMSD 与人工判断。

`warning` 不失败，但会写入报告。**任意** pose 的 geometry error 会让 case
失败，并以 `errorPoses` 记录；不要把“排名第一通过”理解成“全部 pose 都合理”。

### 几何检查是什么

使用项目已有的六项 PoseBusters 风格检查：内部碰撞、键长异常、键角异常、
平面性破坏、手性翻转、盒子外。阈值在
`vinastudio/core/chem/pose_validation.py` 的 `THRESHOLDS` 中集中定义。

**这不是官方 PoseBusters 套件**，不能把本文件的通过率写成 PoseBusters
通过率，也不能据此外推所有靶点。内部碰撞检查只检查重原子：PDBQT 省略非极性
氢坐标，Meeko 在对接后重建氢；`internal_clash` 不把重建氢的位置当作碰撞证据。
这条限制写在报告 §3.4。

## 4. 本机基线（2026-10-29）

环境：VinaStudio 0.6.4；Python 3.12.14；Vina 1.2.7；Meeko 0.8.0；
RDKit 2026.9.1；NumPy 2.5.4；Linux x86_64；vina Python API。命令：

```bash
uv run python scripts/validate_benchmark.py --case 1iep
```

| Case | 结果 | 排名第一 affinity | 排名第一 RMSD | poses | error poses | 备注 |
|---|---|---:|---:|---:|---:|---|
| 1iep | passed | −13.286 | 0.353 Å | 5 | 0 | 独立 PDB 晶体参考；2702 受体原子 / 40 配体原子 |
| 2hyy | failed（可选本地、自引用） | −12.611 | 1.117 Å | 1 | 0 | reference 与 ligand 同一文件，不作为独立 redocking 证据；62 个残基被排除；组氨酸默认 HIE |

这些值是**本机、本版本、seed 42** 的结果，不是跨平台常数；不要把它写成
“VinaStudio 在 CASF 上的通过率”。1IEP 的参考由完整 1IEP PDB 的
`STI A 201` 坐标生成，图/键级/电荷仍来自教程 SDF；参考路径分离，但不是化学独立
的第二次实验。2hyy 是自引用，harness 现在会判为 failed，不能作为通过证据。

2026-10-23 增加盒子/受体交集检查后，1iep 的通过状态和亲和力基线未改变；这是
“没有把错误结果改成绿色”的证据。当前 0.353 Å 来自 0.6.3 的固定坐标系
`CalcRMS`；旧的 0.260 Å 使用叠加式 RMSD，不能直接比较。

## 5. Manifest 格式

`validation/manifest.json`：

```json
{
  "formatVersion": "1.0",
  "cases": [
    {
      "id": "1iep",
      "name": "c-Abl kinase + imatinib",
      "receptor": "vinastudio/resources/sample/1iep/1iep_receptorH.pdb",
      "ligand": "vinastudio/resources/sample/1iep/1iep_ligand.sdf",
      "reference": "vinastudio/resources/sample/1iep/1iep_reference.sdf",
      "referenceSource": "RCSB PDB 1IEP, HETATM STI A 201; extracted by scripts/build_1iep_reference.py",
      "center": [15.19, 53.903, 16.917],
      "size": [20.0, 20.0, 20.0],
      "exhaustiveness": 8,
      "nPoses": 9,
      "seed": 42,
      "rmsdThreshold": 2.0,
      "affinityRange": [-14.5, -11.0]
    }
  ]
}
```

字段：

- `receptor`/`ligand`/`reference`：相对仓库根或绝对路径；`reference` 必须是
  与 receptor 同一坐标系的共晶配体，且不应与 `ligand` 是同一个文件。
- `referenceSource`：可选的人类可读来源说明，写入报告 provenance。
- `center` + `size`：显式盒子；两者要么都给，要么都不给。
- 都不给时用 `reference` 的 heavy atoms 自动定盒，`extend`（默认 4 Å）加到每侧。
- `exhaustiveness`、`nPoses`、`seed`、`scoring`：对该 case 的 Vina 参数。
- `rmsdThreshold`：默认 2.0 Å。
- `affinityRange`：可选；只用于“是否落在本 case 预期区间”，不是亲和力预测。
- `allowBadResidues`：界面默认 true（可在设置中改为默认关闭），API 默认 false；
  只有在你明确接受 Meeko 模板排除时才开，排除项会写入报告。

## 6. 扩展到 10–20 个体系

harness 本身支持任意数量的 case，但**没有在仓库里内置 10–20 个 PDB/PDBbind
数据**（体积、许可、下载稳定性）。正确做法：

1. 从 PDBbind/CASF/PoseBusters 等你获授权的数据中选体系；
2. 准备同一坐标系的 receptor、ligand、reference（reference 必须是共晶配体）；
3. 用 canonical SMILES 校验 ligand/reference 是同一化学结构；
4. 有共晶配体时用显式盒子或 `reference` autobox；记录盒子来源；
5. 加进**你自己的 manifest**（不要改默认文件冒充覆盖），运行并保留报告；
6. 只报告你实际跑过的体系；缺失/跳过要显式写。

当前默认只有 **1 个有效对照（1IEP）**；2HYY 在独立的 optional manifest 中，
且因自引用被 harness 判为 failed。不能据此声称“10–20 体系验证完成”。数据集
扩展应作为独立工作项，先解决参考配体/坐标/许可，再谈数量。完整限制、引用和证据矩阵见
[ACADEMIC_VALIDATION.zh-CN.md](ACADEMIC_VALIDATION.zh-CN.md)。

## 7. 与旧脚本的关系

- `scripts/validate_experiment.py`：历史的一次性 1iep 上游输出对照；
- `scripts/validate_multi_system.py`：历史的多体系探针，含参数范围自证；
- 两者都已标记 legacy，**不再作为当前验证证据**；
- 当前入口只有 `scripts/validate_benchmark.py`。

## 8. 不做的声明

- 不把 Vina affinity 当实验结合自由能；
- 不跨打分函数比较；
- 不声称官方 PoseBusters 通过率；
- 不把 1 个有效 case（或可选负对照）的结果外推为普适精度；
- 不修改准备/对接算法来“让验证变绿”。

## 9. 功能验证记录（独立于 docking 精度）

对接精度验证回答“1IEP 的重对接是否恢复晶体姿态”；功能验证回答“用户可见
入口是否按契约工作”。两者不能互相替代。

- 协议、功能矩阵、证据等级与未执行项：
  [`validation/functional/README.md`](../validation/functional/README.md)
- 2026-10-30 的实际记录（环境、输入哈希、pytest JUnit、前端检查、11 条 UI
  路由冒烟、截图和缺陷复现）：
  [`validation/functional/records/2026-10-30/`](../validation/functional/records/2026-10-30/)
- 机器可读索引：
  [`functional-report.json`](../validation/functional/records/2026-10-30/functional-report.json)

该记录明确保留 `partial` / `not-run` 项（完整 125 分子筛选、site screening、
桌面原生对话框、在线化合物源、GPU 渲染），不会把“页面能打开”写成“功能通过”。
