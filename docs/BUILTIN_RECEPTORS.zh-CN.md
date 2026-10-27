# 内置本科药物靶点结构库

[English](BUILTIN_RECEPTORS.md)

VinaStudio 内置一套 **27 个药物靶点蛋白结构**，面向药理学与药物化学本科
教学。它们是 Catalog 中的 **受体** 分子，放在集合里而不是筛选库——筛选库
是配体输入，不能被误当作虚拟筛选的配体集合。

## 包含内容

- 激酶：ABL1（1IEP）、EGFR（1M17）、PKA（1ATP）、CDK2（1HCK）、Src（2SRC）。
- 酶：HMG-CoA 还原酶（1HWK）、乙酰胆碱酯酶（1EVE）、流感病毒神经氨酸酶
  （1B9V）、DHFR（1DHF）、ACE（1O86）、COX-1（1EQG）、COX-2（5KIR）、
  MAO-A（2Z5X）、MAO-B（2V5Z）。
- 蛋白酶：HIV-1 蛋白酶（1HSG）。
- 核受体：ERα（1ERE）、雄激素受体（1E3G）、糖皮质激素受体（1M2Z）、
  PPARγ（2PRG）。
- GPCR：β2 肾上腺素受体（2RH1）、M2 毒蕈碱受体（3UON）、D2 多巴胺受体
  （6CM4）、H1 组胺受体（3RZE）、μ 阿片受体（4DKL）。
- 转运体：5-羟色胺转运体 SERT（5I6X）。
- 离子通道：GABA-A（6D6U）、hERG（5VA1）。

每条记录包含 PDB ID、靶点/基因、靶点类别、物种、链、共晶配体（如有）、
分辨率、方法和构建体备注。Catalog 中的**蛋白分子量**按沉积坐标中建模的
蛋白残基计算，不含共晶配体、水和缺失残基，因此不等于完整基因产物的质量。PDB 文件随安装包放在
`vinastudio/resources/catalog/receptors/`，来源链接指向 RCSB。

## 科学边界

- 这些是**带有构建体/融合标签的实验结构**，不一定等于野生型人蛋白。
  多个 GPCR 结构含 T4 溶菌酶或 BRIL 融合；5I6X 含 Fab 伴侣链；6D6U 是
  多亚基 GABA-A 复合物；1M2Z/2PRG 含共激活肽；1ATP 含 PKI 抑制肽。
  默认准备会保留蛋白链并去除水和杂原子；解释对接结果前应检查构建体。
- 分辨率从 1.5 Å 到 3.92 Å。低分辨率和冷冻电镜结构用于教学覆盖，不应
  作为基准级对接受体。
- 设置中的 **“默认允许模板匹配失败的残基”** 开启时，27 个结构目前都能准备；
  其中 13 个（工程化 GPCR、模板缺失/末端残基、hERG 冷冻电镜模型）在不开启
  该选项时会失败，准备报告会列出被排除的残基。需要更严格的 Meeko 检查时可在
  设置中关闭默认值，单个准备对话框仍可单独覆盖。
- PDB 条目是结构，不是疾病模型或临床靶点结论；对接分数是教学假设，
  不是实验亲和力。
- 受体只在工作区首次访问时播种一次，生成普通 Catalog 对象，可重命名、
  准备、移除或删除；删除集合后不会在下次启动自动回灌。

## 书目依据

- 《药理学》（人民卫生出版社，杨宝峰/陈建国主编）
- 《药物化学》（人民卫生出版社，尤启冬主编）
- Goodman & Gilman's *The Pharmacological Basis of Therapeutics*
- Katzung's *Basic & Clinical Pharmacology*
- Rang & Dale's *Pharmacology*
- Foye's *Principles of Medicinal Chemistry*

书目用于靶点选择；结构与元数据来自 RCSB PDB。

## 数据与来源

- 文件：`vinastudio/resources/catalog/undergraduate_receptors.csv`
- PDB：`vinastudio/resources/catalog/receptors/*.pdb`
- 来源：RCSB PDB（`https://www.rcsb.org/structure/<PDB>`）
- 标记：`builtin_undergrad_receptors_v1`
- 测试通过 `VINASTUDIO_BUILTIN_LIBRARY_SEED=0` 禁用播种；真实工作区首次
  访问 Catalog 时播种。
