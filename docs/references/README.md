# 参考论文（实现依据）

本目录保存**我们据以实现算法的原始文献**。目的：算法参数与判据必须**可追溯到
公开文献**，而不是「调出来看着对」。代码里出现这些常量时，注释指向本文献。

## 收录

| 文件 | 文献 | 用途 |
|---|---|---|
| `fpocket-2009-bmc-bioinformatics.pdf` | Le Guilloux V, Schmidtke P, Tuffery P. **Fpocket: An open source platform for ligand pocket detection.** *BMC Bioinformatics* 10:168 (2009). doi:[10.1186/1471-2105-10-168](https://doi.org/10.1186/1471-2105-10-168) | **主依据**：alpha 球定义、标准参数、三级聚类、五描述子打分、命中率基准 |
| `p2rank-2018-j-cheminform.pdf` | Krivák R, Hoksza D. **P2Rank: machine learning based tool for rapid and accurate prediction of ligand binding sites from protein structure.** *J Cheminform* 10:39 (2018). doi:[10.1186/s13321-018-0285-8](https://doi.org/10.1186/s13321-018-0285-8) | 对照：另一条路线（表面点 + 化学/几何特征的机器学习），说明**纯几何排序不足** |

## 我们从 fpocket 论文照用的常量（`vinastudio/core/pocket.py`）

| 参数 | 值 | 出处 |
|---|---|---|
| alpha 球半径区间 | **3.0 – 6.0 Å** | 论文 §Parameter optimisation（标准参数） |
| 三级聚类连接距离 | **1.73 / 2.5 / 4.0 Å** | 同上 |
| 每口袋最少 alpha 球 | **35** | 同上 |
| 非极性球判据 | 接触 ≥3 个**电负性 < 2.8** 的原子（C/S） | 论文 §Clustering of alpha spheres |
| 排序描述子（5 个） | 归一化球数、平均局部疏水密度、非极性球比例、极性分数（残基极性）、球密度 | 论文 §Scoring function（PLS） |

## 校准用的公开命中率（验收门槛不能凭感觉定）

判据：口袋中心距**任一**配体原子 ≤ 4 Å（论文的 PocketPicker criterion）。

| | 前 1 | 前 3 |
|---|---|---|
| holo（结合态） | 83% | **92%** |
| apo（未结合态） | 69% | **94%** |

→ 因此本项目的验收断言是「**已知位点落在前 3**」，不是前 1。论文亦明言：
「最大口袋常对应真实位点，但这条规律不能一般化」。

## 许可与边界（重要）

- **两篇论文均为开放获取**（BMC / SpringerOpen，CC BY），本目录的收录属于
  允许的再分发，署名见上表。
- **fpocket 的软件本体是 GNU GPL**（论文 §Availability 明载；另有第三方资料写
  MIT，存在不一致）。本项目**只按论文描述自行实现，不阅读、不复制、不链接
  fpocket 源码**——沿用 `AGENTS.md` 既有的 GPL 隔离先例（MolEditPy 作行为规格）。
- 第三方网页指南（如 Talindrew 的 P2Rank vs fpocket 对比）**只作为线索**，
  未收录其正文；需要时按 URL 引用，不作为实现依据。

## Academic-validation bibliography (0.6.4 report)

Metadata below was resolved through Crossref on **2026-10-29**; PDB entries
were checked against RCSB. The report cites only entries that support a named
claim. Paywalled PDFs are deliberately **not** redistributed; the DOI is the
stable access point.

| Key | Citation | DOI / access | Local PDF |
|---|---|---|---|
| `trott2010vina` | Trott O, Olson AJ. *J Comput Chem* 31(2):455–461 (2010). | [10.1002/jcc.21334](https://doi.org/10.1002/jcc.21334) | no (publisher) |
| `eberhardt2021vina` | Eberhardt J, Santos-Martins D, Tillack AF, Forli S. *J Chem Inf Model* 61(8):3891–3898 (2021). | [10.1021/acs.jcim.1c00203](https://doi.org/10.1021/acs.jcim.1c00203) | no |
| `morris2009autodock4` | Morris GM, Huey R, Lindstrom W, Sanner MF, Belew RK, Goodsell DS, Olson AJ. *J Comput Chem* 30(16):2785–2791 (2009). | [10.1002/jcc.21256](https://doi.org/10.1002/jcc.21256) | no |
| `quiroga2016vinardo` | Quiroga R, Villarreal MA. *PLOS ONE* 11(5):e0155183 (2016). | [10.1371/journal.pone.0155183](https://doi.org/10.1371/journal.pone.0155183), CC BY 4.0 | `quiroga-2016-vinardo-plos-one.pdf` |
| `santos2025meeko` | Santos-Martins D, He Y, Eberhardt J, et al. *J Chem Inf Model* 65(24):13045–13050 (2025). | [10.1021/acs.jcim.5c02271](https://doi.org/10.1021/acs.jcim.5c02271) | no |
| `riniker2015etkdg` | Riniker S, Landrum GA. *J Chem Inf Model* 55(12):2562–2574 (2015). | [10.1021/acs.jcim.5b00654](https://doi.org/10.1021/acs.jcim.5b00654) | no |
| `buttenschoen2024posebusters` | Buttenschoen M, Morris GM, Deane CM. *Chem Sci* 15(9):3130–3139 (2024). | [10.1039/D3SC04185A](https://doi.org/10.1039/D3SC04185A), CC BY | no (publisher blocks automated PDF fetch) |
| `nagar2002crystal` | Nagar B, Bornmann WG, Pellicena P, et al. *Cancer Res* 62(15):4236–4243 (2002). PMID 12154025. | [PubMed](https://pubmed.ncbi.nlm.nih.gov/12154025/) | no |
| `bissantz2000virtual` | Bissantz C, Folkers G, Rognan D. *J Med Chem* 43(25):4759–4767 (2000). | [10.1021/jm001044l](https://doi.org/10.1021/jm001044l) | no |
| `kellenberger2004comparative` | Kellenberger E, Rodrigo J, Muller P, Rognan D. *Proteins* 57(2):225–242 (2004). | [10.1002/prot.20149](https://doi.org/10.1002/prot.20149) | no |
| `su2019casf` | Su M, Yang Q, Du Y, et al. *J Chem Inf Model* 59(2):895–913 (2019). | [10.1021/acs.jcim.8b00545](https://doi.org/10.1021/acs.jcim.8b00545) | no; not used |
| `pdb1iep` | RCSB PDB 1IEP, c-Abl + imatinib. | [10.2210/pdb1IEP/pdb](https://doi.org/10.2210/pdb1IEP/pdb) | no |
| `pdb2hyy` | RCSB PDB 2HYY, c-Abl + imatinib. | [10.2210/pdb2HYY/pdb](https://doi.org/10.2210/pdb2HYY/pdb) | no |
| `mysinger2012dude` | Mysinger MM, Carchia M, Irwin JJ, Shoichet BK. *J Med Chem* 55(14):6582–6594 (2012). | [10.1021/jm300687e](https://doi.org/10.1021/jm300687e) | no; not used |

Machine-readable entries: [`VinaStudio.bib`](VinaStudio.bib).

### Citation boundaries

- The bundled `quiroga-2016-vinardo-plos-one.pdf` is CC BY 4.0; attribution is
  preserved in this table.
- `PoseBusters` and `Vinardo` are open access; `PoseBusters` is linked rather
  than mirrored because the publisher endpoint refused automated download.
- No paywalled article PDF (Vina, AutoDock4, Meeko, ETKDG, CASF, DUD-E) is
  redistributed.
- PDB coordinates are public structure data; cite the PDB entry and the primary
  structure paper where available.
