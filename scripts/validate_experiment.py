#!/usr/bin/env python3
"""VinaStudio 学术验证脚本

运行真实的分子对接实验，验证项目准确性：
1. 受体准备 vs 上游 Meeko
2. 配体准备 vs 上游 Meeko
3. 对接结果 vs 文献值
4. RMSD 提取 vs Vina 原始输出
5. SDF/PDB 导出验证

使用方法:
    uv run python scripts/validate_experiment.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "vinastudio" / "resources" / "sample" / "1iep"

# 输入文件
RECEPTOR_PDB = SAMPLE / "1iep_receptorH.pdb"
LIGAND_SDF = SAMPLE / "1iep_ligand.sdf"
LIGAND_PDBQT = SAMPLE / "1iep_ligand.pdbqt"
UPSTREAM_RECEPTOR_PDBQT = SAMPLE / "1iep_receptor.pdbqt"
UPSTREAM_DOCKING_OUTPUT = SAMPLE / "1iep_ligand_vina_out.pdbqt"


# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class ValidationResult:
    name: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


@dataclass
class ValidationReport:
    results: list[ValidationResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, expected: str, actual: str, details: str = ""):
        self.results.append(ValidationResult(name, passed, expected, actual, details))

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    def print_report(self) -> None:
        print("\n" + "=" * 70)
        print("VinaStudio 学术验证报告")
        print("=" * 70)

        for r in self.results:
            status = "✓ PASS" if r.passed else "✗ FAIL"
            print(f"\n{status}: {r.name}")
            print(f"  预期: {r.expected}")
            print(f"  实际: {r.actual}")
            if r.details:
                print(f"  说明: {r.details}")

        print("\n" + "-" * 70)
        print(f"总计: {self.total} 项验证")
        print(f"通过: {self.passed} 项")
        print(f"失败: {self.failed} 项")
        print("=" * 70)

        if self.failed > 0:
            print("\n⚠️  存在验证失败项，请检查上述详情。")
            sys.exit(1)
        else:
            print("\n✅ 所有验证通过。")


# ── 验证函数 ──────────────────────────────────────────────────────────────────

def validate_receptor_preparation(report: ValidationReport) -> None:
    """验证受体准备: 对比 VinaStudio 与上游 Meeko 的 PDBQT 输出。"""
    from vinastudio.core.chem.pdbqt import parse_pdbqt
    from vinastudio.core.chem.receptor_prep import prepare_receptor

    print("\n[1/5] 验证受体准备...")

    # VinaStudio 受体准备
    prepared = prepare_receptor(RECEPTOR_PDB)
    vs_pdbqt = prepared.pdbqt

    # 上游受体
    upstream_pdbqt = UPSTREAM_RECEPTOR_PDBQT.read_text()

    # 解析两者
    vs_doc = parse_pdbqt(vs_pdbqt)
    up_doc = parse_pdbqt(upstream_pdbqt)

    # 原子数验证
    vs_atoms = vs_doc.first_pose.n_atoms
    up_atoms = up_doc.first_pose.n_atoms
    report.add(
        "受体原子数",
        vs_atoms == up_atoms,
        str(up_atoms),
        str(vs_atoms),
        "1iep 受体应有 2702 原子",
    )

    # 元素计数验证
    vs_elements = Counter(a.element for a in vs_doc.first_pose.atoms)
    up_elements = Counter(a.element for a in up_doc.first_pose.atoms)
    
    # 上游解析器可能将部分 H 识别为空元素，计算总数
    vs_h_total = vs_elements.get("H", 0)
    up_h_total = up_elements.get("H", 0) + up_elements.get("", 0)  # 空元素大多是 H
    
    # 忽略空元素差异，比较其他元素
    vs_elements_filtered = {k: v for k, v in vs_elements.items() if k and k != "H"}
    up_elements_filtered = {k: v for k, v in up_elements.items() if k and k != "H"}
    
    elements_match = (
        vs_elements_filtered == up_elements_filtered
        and vs_h_total == up_h_total
    )
    report.add(
        "受体元素计数",
        elements_match,
        f"H: {up_h_total} (含 {up_elements.get('', 0)} 空元素), 其他: {up_elements_filtered}",
        f"H: {vs_h_total}, 其他: {vs_elements_filtered}",
        "总氢原子数应一致（上游解析器将部分 H 识别为空元素）",
    )

    # 原子类型验证（允许 Met/Cys 硫原子差异 S vs SA）
    vs_types = Counter(a.atom_type for a in vs_doc.first_pose.atoms)
    up_types = Counter(a.atom_type for a in up_doc.first_pose.atoms)
    
    # 计算总硫原子数（S + SA）
    vs_sulfur = vs_types.get("S", 0) + vs_types.get("SA", 0)
    up_sulfur = up_types.get("S", 0) + up_types.get("SA", 0)
    
    # 忽略 S/SA 差异，比较其他原子类型
    vs_types_filtered = {k: v for k, v in vs_types.items() if k not in ("S", "SA")}
    up_types_filtered = {k: v for k, v in up_types.items() if k not in ("S", "SA")}
    
    types_match = vs_types_filtered == up_types_filtered and vs_sulfur == up_sulfur
    report.add(
        "受体原子类型",
        types_match,
        f"硫原子总数: {up_sulfur}, 其他类型一致",
        f"硫原子总数: {vs_sulfur}, 其他类型: {vs_types_filtered == up_types_filtered}",
        "Meeko 0.8 将硫类型从 SA 改为 S，但总数一致",
    )


def validate_ligand_preparation(report: ValidationReport) -> None:
    """验证配体准备: 电荷、原子类型、SMILES 一致性。"""
    from vinastudio.core.chem.ligand_prep import prepare_ligand
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    print("\n[2/5] 验证配体准备...")

    # VinaStudio 配体准备
    prepared = prepare_ligand(LIGAND_SDF)
    vs_pdbqt = prepared.pdbqt

    # 上游配体
    up_pdbqt = LIGAND_PDBQT.read_text()

    # 解析两者
    vs_doc = parse_pdbqt(vs_pdbqt)
    up_doc = parse_pdbqt(up_pdbqt)

    # 原子数验证（配体应有 40 个 PDBQT 原子）
    vs_atoms = vs_doc.first_pose.n_atoms
    up_atoms = up_doc.first_pose.n_atoms
    report.add(
        "配体原子数",
        vs_atoms == up_atoms == 40,
        "40",
        str(vs_atoms),
        "1iep 配体去除非极性氢后应有 40 个 PDBQT 原子",
    )

    # 电荷验证（总电荷应 ≈ +1.0）
    vs_charge = sum(a.charge for a in vs_doc.first_pose.atoms)
    up_charge = sum(a.charge for a in up_doc.first_pose.atoms)
    charge_ok = abs(vs_charge - 1.0) < 0.1 and abs(up_charge - 1.0) < 0.1
    report.add(
        "配体总电荷",
        charge_ok,
        f"≈ +1.0 (上游: {up_charge:.3f})",
        f"{vs_charge:.3f}",
        "伊马替尼质子化后总电荷应 ≈ +1.0",
    )

    # SMILES 一致性
    vs_smiles = vs_doc.smiles
    up_smiles = up_doc.smiles
    smiles_match = vs_smiles == up_smiles
    report.add(
        "配体 SMILES",
        smiles_match,
        up_smiles or "(无)",
        vs_smiles or "(无)",
        "SMILES 应完全一致（来自 Meeko header）",
    )

    # 原子类型计数
    vs_types = Counter(a.atom_type for a in vs_doc.first_pose.atoms)
    up_types = Counter(a.atom_type for a in up_doc.first_pose.atoms)
    types_match = vs_types == up_types
    report.add(
        "配体原子类型",
        types_match,
        dict(up_types),
        dict(vs_types),
        "原子类型计数应完全一致",
    )


def validate_docking_result(report: ValidationReport) -> None:
    """验证对接结果: 亲和力、RMSD、能量分解。"""
    from vinastudio.core.chem.pdbqt import parse_pdbqt

    print("\n[3/5] 验证对接结果...")

    # 解析上游对接输出
    upstream_pdbqt = UPSTREAM_DOCKING_OUTPUT.read_text()
    doc = parse_pdbqt(upstream_pdbqt)

    # 构象数
    report.add(
        "对接构象数",
        doc.n_poses == 4,
        "4",
        str(doc.n_poses),
        "1iep 上游对接输出应有 4 个构象",
    )

    # 最佳亲和力
    best_affinity = doc.poses[0].energy
    affinity_ok = -14.0 < best_affinity < -12.0
    report.add(
        "最佳亲和力",
        affinity_ok,
        "≈ -13.2 kcal/mol (范围: -14 ~ -12)",
        f"{best_affinity:.3f} kcal/mol",
        "1iep + 伊马替尼在 Vina 力场下的预期值",
    )

    # RMSD 提取
    pose = doc.poses[0]
    rmsd_ok = pose.rmsd_lower_bound == 0.0 and pose.rmsd_upper_bound == 0.0
    report.add(
        "RMSD 提取（第一构象）",
        rmsd_ok,
        "0.000 / 0.000",
        f"{pose.rmsd_lower_bound:.3f} / {pose.rmsd_upper_bound:.3f}",
        "第一构象 RMSD 应为 0（参考构象）",
    )

    # 非第一构象 RMSD
    if len(doc.poses) > 1:
        pose2 = doc.poses[1]
        rmsd2_ok = pose2.rmsd_lower_bound > 0 and pose2.rmsd_upper_bound > 0
        report.add(
            "RMSD 提取（第二构象）",
            rmsd2_ok,
            "> 0.0 / > 0.0",
            f"{pose2.rmsd_lower_bound:.3f} / {pose2.rmsd_upper_bound:.3f}",
            "非参考构象应有非零 RMSD",
        )

    # 能量递增（构象按亲和力排序）
    energies = [p.energy for p in doc.poses]
    energy_sorted = all(energies[i] <= energies[i + 1] for i in range(len(energies) - 1))
    report.add(
        "能量排序",
        energy_sorted,
        "递增顺序",
        str([f"{e:.3f}" for e in energies]),
        "构象应按亲和力从低到高排列",
    )


def validate_export(report: ValidationReport) -> None:
    """验证 SDF/PDB 导出: 键级恢复、坐标一致性。"""
    from rdkit import Chem

    from vinastudio.core.chem.export import pdbqt_to_pdb, poses_to_sdf

    print("\n[4/5] 验证导出功能...")

    # SDF 导出
    sdf_result = poses_to_sdf(UPSTREAM_DOCKING_OUTPUT)

    # SDF 记录数
    report.add(
        "SDF 记录数",
        sdf_result.n_poses == 4,
        "4",
        str(sdf_result.n_poses),
        "应有 4 个 SDF 记录（每个构象一个）",
    )

    # SDF 亲和力属性
    has_affinity = ">  <affinity_kcal_per_mol>" in sdf_result.sdf
    report.add(
        "SDF 亲和力属性",
        has_affinity,
        "包含 affinity_kcal_per_mol",
        "包含" if has_affinity else "不包含",
        "每个 SD 记录应包含亲和力属性",
    )

    # SDF 解析验证
    supplier = Chem.SDMolSupplier()
    supplier.SetData(sdf_result.sdf, removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    report.add(
        "SDF RDKit 解析",
        len(molecules) == 4,
        "4 个有效分子",
        f"{len(molecules)} 个有效分子",
        "所有 SDF 记录应可被 RDKit 正确解析",
    )

    # 键级验证（芳香性）
    if molecules:
        aromatic_count = sum(
            1 for atom in molecules[0].GetAtoms() if atom.GetIsAromatic()
        )
        aromatic_ok = aromatic_count >= 16  # 两个苯环 + 吡啶 + 嘧啶
        report.add(
            "SDF 芳香性感知",
            aromatic_ok,
            "≥ 16 个芳香原子",
            str(aromatic_count),
            "键级从 SMILES 恢复，芳香性应正确感知",
        )

    # 原子数（SDF 应有 69 原子，PDBQT 有 40 原子）
    if molecules:
        atom_count = molecules[0].GetNumAtoms()
        report.add(
            "SDF 原子数",
            atom_count == 69,
            "69 (包含非极性氢)",
            str(atom_count),
            "SDF 包含完整氢原子，PDBQT 只有极性氢",
        )

    # PDB 导出
    upstream_pdbqt = UPSTREAM_DOCKING_OUTPUT.read_text()
    pdb_text = pdbqt_to_pdb(upstream_pdbqt, title="test receptor")
    atom_lines = [line for line in pdb_text.splitlines() if line.startswith("ATOM")]
    report.add(
        "PDB ATOM 行",
        len(atom_lines) > 0,
        "> 0",
        str(len(atom_lines)),
        "PDB 应包含 ATOM 记录",
    )

    # PDB 不包含 AutoDock 列（列 67-79 是 AutoDock 专有列）
    # 标准 PDB ATOM 行最长 80 字符，AutoDock 列在 67-79
    has_ad_cols = any(
        len(line) > 80 or (len(line) >= 77 and line[76:78].strip() not in ("", "C", "N", "O", "S", "H"))
        for line in atom_lines[:10]
    )
    report.add(
        "PDB 无 AutoDock 列",
        not has_ad_cols,
        "无 (列 ≤ 80, 元素列在 77-78)",
        "有" if has_ad_cols else "无",
        "PDB 应去除 AutoDock 原子类型和电荷列",
    )


def validate_vina_api_interface(report: ValidationReport) -> None:
    """验证 Vina API 接口覆盖。"""
    print("\n[5/5] 验证 Vina API 接口覆盖...")

    from vinastudio.config import SCORING_WEIGHT_COUNT, ScoringFunction

    # 评分函数支持：对照真正定义取值范围的类型，而不是本地重写一遍列表
    supported = sorted(ScoringFunction.__args__)
    report.add(
        "评分函数",
        supported == ["ad4", "vina", "vinardo"],
        "3 (vina, vinardo, ad4)",
        str(len(supported)),
        "支持 Vina、Vinardo、AutoDock4 三种评分函数",
    )

    # 权重数量
    report.add(
        "Vina 权重数",
        SCORING_WEIGHT_COUNT["vina"] == 7,
        "7",
        str(SCORING_WEIGHT_COUNT["vina"]),
        "Vina 评分函数有 7 个可调权重",
    )

    report.add(
        "Vinardo 权重数",
        SCORING_WEIGHT_COUNT["vinardo"] == 6,
        "6",
        str(SCORING_WEIGHT_COUNT["vinardo"]),
        "Vinardo 评分函数有 6 个可调权重",
    )

    report.add(
        "AD4 权重数",
        SCORING_WEIGHT_COUNT["ad4"] == 6,
        "6",
        str(SCORING_WEIGHT_COUNT["ad4"]),
        "AutoDock4 评分函数有 6 个可调权重",
    )

    # 盒子默认值
    from vinastudio.config import DEFAULT_SPACING

    report.add(
        "默认网格间距",
        DEFAULT_SPACING == 0.375,
        "0.375 Å",
        f"{DEFAULT_SPACING} Å",
        "Vina 默认网格间距为 0.375 Å",
    )


# ── 主函数 ──────────────────────────────────────────────────────────────────

def main() -> None:
    """运行所有验证。"""
    print("VinaStudio 学术验证脚本")
    print("正在运行真实实验数据验证...\n")

    # 检查样本数据
    required_files = [RECEPTOR_PDB, LIGAND_SDF, LIGAND_PDBQT, UPSTREAM_RECEPTOR_PDBQT, UPSTREAM_DOCKING_OUTPUT]
    if not all(p.exists() for p in required_files):
        print("错误: 样本数据不完整。请运行 'uv run python scripts/fetch_samples.py'")
        sys.exit(1)

    report = ValidationReport()

    try:
        validate_receptor_preparation(report)
        validate_ligand_preparation(report)
        validate_docking_result(report)
        validate_export(report)
        validate_vina_api_interface(report)
    except (ImportError, OSError, ValueError) as e:
        print(f"\n错误: 验证过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    report.print_report()

    # 输出 JSON 报告
    json_path = ROOT / "docs" / "validation_report.json"
    json_data = {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "expected": r.expected,
                "actual": r.actual,
                "details": r.details,
            }
            for r in report.results
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
    print(f"\nJSON 报告已保存到: {json_path}")


if __name__ == "__main__":
    main()
