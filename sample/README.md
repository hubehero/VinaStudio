# VinaStudio 测试样本

## 目录结构

```
sample/
├── receptors/       # 受体文件 (PDB + mmCIF)
├── ligands/         # 配体文件 (SDF, MOL, MOL2)
├── pdbqt/           # 预处理的 PDBQT 文件 (可选)
└── projects/        # 项目文件 (可选)
```

## 受体样本

| 文件 | 来源 | 说明 |
|------|------|------|
| `1iep_receptor.pdb` | 1IEP | c-Abl 激酶域 + 伊马替尼 (STI) |
| `1hsg_receptor.pdb` | 1HSG | HIV-1 蛋白酶 + 茚地那韦 (MK1) |
| `4hhb_receptor.pdb` | 4HHB | 人脱氧血红蛋白 (HEM) |
| `2hyy_receptor.pdb` | 2HYY | Abl 激酶域 + 伊马替尼 (STI) |
| `3htb_receptor.pdb` | 3HTB | T4 溶菌酶 L99A/M102Q + 2-丙基苯酚 (JZ4) |
| `*.cif` | 同上 | 同一批结构的 mmCIF 版本，用于测试 mmCIF 支持 |

这些是未处理的 PDB 原始条目：共晶配体、离子和水都还在，使用前要在"准备受体"里去除，
这正是这一类样本要覆盖的场景。

## 配体样本

| 文件 | 格式 | 说明 |
|------|------|------|
| `1iep_ligand.sdf` | SDF | 伊马替尼 (STI)，来自 1IEP |
| `2hyy_ligand.sdf` | SDF | 伊马替尼 (STI)，坐标取自 2HYY 的 A 链 |
| `1iep_ligand.mol` | MOL | 与 `1iep_ligand.sdf` 同一分子的 MOL 版本，用于测试 MOL 读取 |
| `1hsg_ligand.sdf` | SDF | 茚地那韦 (MK1)，来自 1HSG |
| `3htb_ligand.sdf` | SDF | FXV 抑制剂 |
| `4hhb_ligand.sdf` | SDF | 血红素 (HEM) |
| `test_ligand.mol2` | MOL2 | 测试用小分子 |
| `batch_test.sdf` | SDF | 批量测试 (2 个分子: p-benzoquinone + phenol) |

## 快速测试流程

### 单分子对接
1. **准备受体**: 上传 `receptors/1iep_receptor.pdb` → 水分子去除 → PDBQT 输出
2. **准备配体**: 上传 `ligands/1iep_ligand.sdf` → 加氢 + 3D 构象 → PDBQT 输出
3. **定义盒子**: 使用 autobox 功能，从配体自动生成
4. **对接**: 使用默认参数运行 Vina 对接
5. **分析**: 查看结合能、构象、相互作用

### 批量对接
1. 上传 `ligands/batch_test.sdf` (包含 2 个分子)
2. 使用批量对接功能
3. 导出 CSV 结果

### mmCIF 测试
1. 上传 `receptors/1iep_receptor.cif`
2. 验证 mmCIF → PDB 转换
3. 正常准备受体

### 格式兼容性测试
- SDF: `1iep_ligand.sdf`, `1hsg_ligand.sdf`
- MOL: `1iep_ligand.mol`
- MOL2: `test_ligand.mol2`
- PDB: 所有受体
- mmCIF: `1iep_receptor.cif`, `1hsg_receptor.cif`, `4hhb_receptor.cif`

## 预期结果

### 1IEP (c-Abl + Imatinib)
- 最佳结合能: ~ -13 kcal/mol
- 盒子中心: (15.190, 53.903, 16.917)
- 盒子大小: 20 Å

### 1HSG (HIV-1 PR + Indinavir)
- 最佳结合能: ~ -10 kcal/mol
- 蛋白酶抑制剂复合物

### 3HTB (Thrombin + FXV)
- 最佳结合能: ~ -9 kcal/mol
- 丝氨酸蛋白酶

## 注意事项

1. 受体文件需要去除水分子和非必需配体
2. 配体需要加氢和 3D 构象优化
3. 对接盒子应覆盖活性位点
4. 批量对接时，每个配体独立处理
5. 这些文件是 RCSB 的原始下载内容，可用
   `https://files.rcsb.org/download/<PDB ID>.pdb`（以及 `.cif`）重新获取；目录本身
   不纳入版本控制（见 `.gitignore`），只有本 README 会被提交。
6. `4hhb_ligand.sdf` 是 RCSB 的 HEM 标准定义：结构可读（RDKit `sanitize=False`
   通过），但 RDKit 无法通过它的价态检查（卟啉环与铁的电荷表示）。因此它只能用于
   文件读写与渲染测试，**不能**用于配体准备。
7. 每个样本文件都必须能被对应工具读入：`tests/unit/test_reference_data.py` 会做这
   项检查。此前 `ligands/` 下有两个文件其实是下载失败的 404 HTML 页面，而
   `batch_test.sdf` 的键数对不上（声明 30 条、实际 32 行），批量对接流程无法使用。
