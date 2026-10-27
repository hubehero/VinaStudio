# 内置本科药物库

[English](BUILTIN_LIBRARY.md)

VinaStudio 内置一套可离线使用、可编辑的 Catalog 初始库，面向药理学与药物
化学本科教学。它是**结构浏览和对接练习的起点**，不是临床用药参考。

## 包含内容

- **125 个小分子药物**，覆盖自主神经、中枢神经、麻醉、心血管、呼吸、消化、
  内分泌、抗微生物、抗肿瘤、抗炎与抗凝等教学类别。
- 英文通用名/常用名、中文常用名、药物类别（英文键 + 中文标签）、PubChem CID、
  分子式与 InChIKey。
- 结构在构建时从 **PubChem** 获取，并用 RDKit 校验：每行都可解析，RDKit
  InChIKey 与 PubChem 一致。
- 每个工作区只播种一次。生成的是普通 Catalog 分子、父集合 + 按大类嵌套的
  子集合（自主神经、中枢、心血管、抗微生物等）和筛选库，因此可以像用户
  数据一样重命名、编辑、删减或删除。**删除后不会在下次启动时自动回灌。**

## 科学范围与边界

- 选择以本科教学中的机制/类别代表性为主，不是处方集，也不包含剂量、适应症、
  禁忌症或临床建议。
- 结构采用 PubChem 对应该名称的记录。盐型、水合物、质子化状态或立体异构体
  可能与某个上市制剂不同；这里的结构记录是对接输入，不代表药学等效性判断。
- 播种的源文件是 **2D SDF**，刻意不是可对接的 3D 结构；请使用 Catalog 的
  正常准备步骤加氢并生成 3D 构象/PDBQT。
- 其中包含受管制药物或有毒参考化合物，仅作为教学结构存在；使用和处置应遵守
  当地规定。
- 本库不是活性/实验数据；对接分数只是教学和比较用的假设，不是实验亲和力。

## 书目依据

类别覆盖参考以下常用本科/研究生教材：

- 《药理学》（人民卫生出版社，杨宝峰/陈建国主编）
- 《药物化学》（人民卫生出版社，尤启冬主编）
- Goodman & Gilman's *The Pharmacological Basis of Therapeutics*
- Katzung's *Basic & Clinical Pharmacology*
- Rang & Dale's *Pharmacology*
- Foye's *Principles of Medicinal Chemistry*

书目用于决定类别覆盖，不复制教材正文；结构与标识来自 PubChem。

## 数据与来源

- 文件：`vinastudio/resources/catalog/undergraduate_drugs.csv`
- 分子来源：`PubChem`，每个分子保存 CID 和来源 URL。
- 数据版本：`1`（`catalog_meta` 标记 `builtin_undergrad_drugs_v1`）。
- 开发时可显式启用播种：`VINASTUDIO_BUILTIN_LIBRARY_SEED=1`；测试默认关闭，
  以保持工作区确定性。

## 相关文档

- [分子目录](MOLECULE_CATALOG.zh-CN.md)
- [使用指南](USER_GUIDE.zh-CN.md)
