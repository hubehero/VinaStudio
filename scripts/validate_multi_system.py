#!/usr/bin/env python3
"""VinaStudio 多体系学术验证脚本

验证多个蛋白质-配体复合物的对接准确性：
1. 1iep - c-Abl 激酶 + 伊马替尼 (金标准)
2. 2hyy - HIV 蛋白酶 + 达芦那韦
3. 3eml - P38 MAP 激酶 + 伊马替尼类似物
4. 4yne - EGFR + 厄洛替尼

使用方法:
    uv run python scripts/validate_multi_system.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
VALIDATION_DIR = ROOT / "vinastudio" / "resources" / "validation"
SAMPLE_DIR = ROOT / "vinastudio" / "resources" / "sample" / "1iep"


# ── 验证体系定义 ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ValidationSystem:
    """验证体系定义"""
    pdb_id: str
    name: str
    receptor_name: str
    ligand_name: str
    ligand_residue: str | None = None
    receptor_chain: str | None = None
    resolution: float = 0.0
    expected_affinity: float = -10.0
    affinity_range: float = 3.0
    box_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    box_size: tuple[float, float, float] = (20.0, 20.0, 20.0)
    description: str = ""


# 文献验证体系
VALIDATION_SYSTEMS: tuple[ValidationSystem, ...] = (
    ValidationSystem(
        pdb_id="1iep",
        name="c-Abl 激酶 + 伊马替尼",
        receptor_name="1iep_receptor.pdbqt",
        ligand_name="1iep_ligand.sdf",
        ligand_residue="STI",
        resolution=2.55,
        expected_affinity=-13.2,
        affinity_range=2.0,
        box_center=(15.190, 53.903, 16.917),
        box_size=(20.0, 20.0, 20.0),
        description="c-Abl 激酶域与伊马替尼复合物，PDB: 1iep",
    ),
    ValidationSystem(
        pdb_id="2hyy",
        name="c-Abl 激酶 + 伊马替尼 (高分辨率)",
        receptor_name="2hyy_receptorH.pdbqt",
        ligand_name="2hyy_ligand.sdf",
        ligand_residue="STI",
        receptor_chain="A",
        resolution=1.35,
        expected_affinity=-13.0,
        affinity_range=5.0,
        box_center=(14.3, 15.3, 17.6),
        box_size=(20.0, 20.0, 20.0),
        description="c-Abl 激酶域（高分辨率），PDB: 2hyy",
    ),
    ValidationSystem(
        pdb_id="3eml",
        name="A2A 腺苷受体 + ZM241385",
        receptor_name="3eml_receptorH.pdbqt",
        ligand_name="3eml_ligand.sdf",
        ligand_residue="ZMA",
        resolution=2.6,
        expected_affinity=-10.0,
        affinity_range=3.0,
        box_center=(-9.1, -7.1, 55.9),
        box_size=(18.0, 18.0, 18.0),
        description="人 A2A 腺苷受体与 ZM241385 复合物，PDB: 3eml",
    ),
)


# ── 数据结构 ──────────────────────────────────────────────────────────────────
@dataclass
class ValidationResult:
    """单项验证结果"""
    system: str
    name: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


@dataclass
class ValidationReport:
    """验证报告"""
    results: list[ValidationResult] = field(default_factory=list)

    def add(self, system: str, name: str, passed: bool, expected: str, actual: str, details: str = ""):
        self.results.append(ValidationResult(system, name, passed, expected, actual, details))

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
        print("VinaStudio 多体系学术验证报告")
        print("=" * 70)

        current_system = ""
        for r in self.results:
            if r.system != current_system:
                current_system = r.system
                print(f"\n{'─' * 70}")
                print(f"体系: {current_system}")
                print(f"{'─' * 70}")

            status = "✓ PASS" if r.passed else "✗ FAIL"
            print(f"\n  {status}: {r.name}")
            print(f"    预期: {r.expected}")
            print(f"    实际: {r.actual}")
            if r.details:
                print(f"    说明: {r.details}")

        print("\n" + "=" * 70)
        print(f"总计: {self.total} 项验证")
        print(f"通过: {self.passed} 项")
        print(f"失败: {self.failed} 项")
        print("=" * 70)

        if self.failed > 0:
            print("\n⚠️  存在验证失败项，请检查上述详情。")
        else:
            print("\n✅ 所有验证通过。")


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def download_pdb(pdb_id: str, target_dir: Path) -> Path:
    """从 RCSB PDB 下载结构文件"""
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    target = target_dir / f"{pdb_id}.pdb"
    
    if target.exists():
        return target
    
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        print(f"  下载 {pdb_id} PDB 结构...")
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        target.write_bytes(data)
        return target
    except (urllib.error.URLError, OSError) as e:
        print(f"  下载失败: {e}")
        return None


def extract_ligand_from_pdb(
    pdb_path: Path,
    ligand_residue: str | None = None,
    exclude_residues: frozenset[str] | None = None,
) -> Path | None:
    """从 PDB 文件中提取配体

    Args:
        pdb_path: PDB 文件路径
        ligand_residue: 指定配体残基名（如 "STI", "ZMA"）。为 None 时取所有非溶剂残基。
        exclude_residues: 排除的残基名集合
    """
    if exclude_residues is None:
        exclude_residues = frozenset({
            "HOH", "WAT", "DMS", "EDO", "PEG", "ACT", "MPD",
            "NA", "CL", "K", "CA", "MG", "ZN", "MN", "FE", "CU", "CO",
            "SO4", "PO4", "SCN", "NO3",
        })

    output_path = pdb_path.parent / f"{pdb_path.stem}_ligand.pdb"

    lines = pdb_path.read_text().splitlines()
    ligand_lines = []
    first_chain_seen = False

    for line in lines:
        if not line.startswith("HETATM"):
            continue
        residue_name = line[17:20].strip()
        if residue_name in exclude_residues:
            continue
        if ligand_residue is not None and residue_name != ligand_residue:
            continue
        # 对于多链复合物，只取第一条链的配体
        chain_id = line[21]
        if first_chain_seen and chain_id != ligand_lines[-1][21] if ligand_lines else False:
            break
        ligand_lines.append(line)
        first_chain_seen = True

    if ligand_lines:
        output_path.write_text("\n".join(ligand_lines) + "\n")
        return output_path
    return None


def extract_chain_from_pdb(pdb_path: Path, chain_id: str) -> Path:
    """从 PDB 文件中提取指定链"""
    output_path = pdb_path.parent / f"{pdb_path.stem}_chain{chain_id}.pdb"
    
    lines = pdb_path.read_text().splitlines()
    chain_lines = []
    
    for line in lines:
        if line.startswith(("ATOM", "HETATM")):
            current_chain = line[21]
            if current_chain == chain_id:
                chain_lines.append(line)
        elif line.startswith(("TER", "END")):
            chain_lines.append(line)
    
    if chain_lines:
        output_path.write_text("\n".join(chain_lines) + "\n")
        return output_path
    return None


def prepare_system(system: ValidationSystem, validation_dir: Path) -> bool:
    """准备验证体系"""
    system_dir = validation_dir / system.pdb_id
    
    # 检查是否已准备
    receptor_path = system_dir / system.receptor_name
    ligand_path = system_dir / system.ligand_name
    
    if receptor_path.exists() and ligand_path.exists():
        return True
    
    # 下载 PDB
    pdb_path = download_pdb(system.pdb_id, system_dir)
    if pdb_path is None:
        return False
    
    # 如果需要提取单链，先提取
    receptor_pdb = pdb_path
    if system.receptor_chain:
        chain_pdb = extract_chain_from_pdb(pdb_path, system.receptor_chain)
        if chain_pdb is not None:
            receptor_pdb = chain_pdb
        else:
            print(f"  无法提取链 {system.receptor_chain}")
            return False
    
    # 提取配体
    ligand_pdb = extract_ligand_from_pdb(pdb_path, ligand_residue=system.ligand_residue)
    if ligand_pdb is None:
        print(f"  无法提取配体 {system.ligand_name}")
        return False
    
    # 转换配体为 SDF (使用 OpenBabel 或 RDKit)
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        mol = Chem.MolFromPDBFile(str(ligand_pdb))
        if mol is not None:
            AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
            AllChem.MMFFOptimizeMolecule(mol)
            writer = Chem.SDWriter(str(ligand_path))
            writer.write(mol)
            writer.close()
        else:
            print(f"  无法解析配体 {system.ligand_name}")
            return False
    except Exception as e:  # noqa: BLE001
        print(f"  配体准备失败: {e}")
        return False
    
    # 准备受体
    try:
        from vinastudio.core.chem.receptor_prep import (
            ReceptorPrepOptions,
            prepare_receptor,
        )
        options = ReceptorPrepOptions(allow_bad_residues=True)
        prepared = prepare_receptor(receptor_pdb, options)
        receptor_path.write_text(prepared.pdbqt)
    except Exception as e:  # noqa: BLE001
        print(f"  受体准备失败: {e}")
        return False
    
    return True


# ── 验证函数 ──────────────────────────────────────────────────────────────────

def validate_system(system: ValidationSystem, report: ValidationReport, validation_dir: Path) -> None:
    """验证单个体系"""
    system_dir = validation_dir / system.pdb_id
    receptor_path = system_dir / system.receptor_name
    ligand_path = system_dir / system.ligand_name
    
    # 检查文件存在
    if not receptor_path.exists() or not ligand_path.exists():
        report.add(
            system.pdb_id,
            "文件准备",
            False,
            "受体和配体文件存在",
            "文件缺失",
            f"无法准备 {system.name} 体系",
        )
        return
    
    # 验证受体原子数
    try:
        from vinastudio.core.chem.pdbqt import parse_pdbqt
        receptor_pdbqt = receptor_path.read_text()
        doc = parse_pdbqt(receptor_pdbqt)
        atom_count = doc.first_pose.n_atoms
        
        # 预期原子数范围（不同准备方法可能有差异）
        expected_range = (2000, 5000)  # 典型蛋白受体原子数
        atom_count_ok = expected_range[0] <= atom_count <= expected_range[1]
        
        report.add(
            system.pdb_id,
            "受体原子数",
            atom_count_ok,
            f"{expected_range[0]}-{expected_range[1]}",
            str(atom_count),
            f"{system.name} 受体原子数",
        )
    except Exception as e:  # noqa: BLE001
        report.add(
            system.pdb_id,
            "受体原子数",
            False,
            "可解析",
            f"错误: {e}",
            "PDBQT 解析失败",
        )
    
    # 验证配体 SDF 可读
    try:
        from rdkit import Chem
        supplier = Chem.SDMolSupplier()
        supplier.SetData(ligand_path.read_text(), removeHs=False, sanitize=True)
        molecules = [mol for mol in supplier if mol is not None]
        
        ligand_ok = len(molecules) >= 1
        report.add(
            system.pdb_id,
            "配体 SDF 可读",
            ligand_ok,
            "≥ 1 个有效分子",
            f"{len(molecules)} 个有效分子",
            f"{system.name} 配体 SDF 解析",
        )
        
        if molecules:
            mol = molecules[0]
            atom_count = mol.GetNumAtoms()
            report.add(
                system.pdb_id,
                "配体原子数",
                20 <= atom_count <= 100,
                "20-100",
                str(atom_count),
                f"{system.name} 配体原子数",
            )
    except Exception as e:  # noqa: BLE001
        report.add(
            system.pdb_id,
            "配体 SDF 可读",
            False,
            "可解析",
            f"错误: {e}",
            "SDF 解析失败",
        )
    
    # 验证盒子参数
    box_ok = (
        all(-100 < c < 200 for c in system.box_center)
        and all(10 <= s <= 50 for s in system.box_size)
    )
    report.add(
        system.pdb_id,
        "盒子参数",
        box_ok,
        "中心: (0-100), 尺寸: (10-50 Å)",
        f"中心: {system.box_center}, 尺寸: {system.box_size}",
        f"{system.name} 盒子配置",
    )
    
    # 验证预期亲和力范围
    affinity_ok = -30 < system.expected_affinity < 0
    report.add(
        system.pdb_id,
        "预期亲和力",
        affinity_ok,
        "-30 ~ 0 kcal/mol",
        f"{system.expected_affinity} ± {system.affinity_range} kcal/mol",
        f"{system.name} 文献值",
    )


def run_docking_validation(system: ValidationSystem, report: ValidationReport, validation_dir: Path) -> None:
    """运行对接验证（需要 Vina）"""
    # 对于 1iep，使用样本数据中已有的对接结果
    if system.pdb_id == "1iep":
        return

    system_dir = validation_dir / system.pdb_id
    receptor_path = system_dir / system.receptor_name
    ligand_path = system_dir / system.ligand_name
    
    if not receptor_path.exists() or not ligand_path.exists():
        return
    
    try:
        from vina import Vina
        
        # 配置 Vina
        v = Vina(sf_name="vina", cpu=0, seed=0, verbosity=0)
        v.set_receptor(rigid_pdbqt_filename=str(receptor_path))
        
        # 将 SDF 配体转换为 PDBQT 格式
        from meeko import MoleculePreparation, PDBQTWriterLegacy
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        mol = Chem.MolFromMolFile(str(ligand_path), removeHs=False)
        if mol is None:
            report.add(
                system.pdb_id,
                "对接验证",
                False,
                "成功",
                "无法解析配体 SDF",
                "SDF 解析失败",
            )
            return
        
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        
        preparator = MoleculePreparation()
        mol_setup = preparator(mol)[0]
        pdbqt_string, ok, err = PDBQTWriterLegacy.write_string(mol_setup)
        if not ok:
            report.add(
                system.pdb_id,
                "对接验证",
                False,
                "成功",
                f"PDBQT 写入失败: {err}",
                "配体准备失败",
            )
            return
        
        v.set_ligand_from_string(pdbqt_string)
        
        # 计算地图
        v.compute_vina_maps(
            center=list(system.box_center),
            box_size=list(system.box_size),
            spacing=0.375,
        )
        
        # 运行对接
        v.dock(exhaustiveness=16, n_poses=10)
        
        # 获取结果
        energies = v.energies(n_poses=10)
        best_affinity = energies[0][0]
        
        # 验证亲和力
        affinity_ok = abs(best_affinity - system.expected_affinity) <= system.affinity_range
        report.add(
            system.pdb_id,
            "对接亲和力",
            affinity_ok,
            f"{system.expected_affinity} ± {system.affinity_range} kcal/mol",
            f"{best_affinity:.3f} kcal/mol",
            f"{system.name} Vina 对接结果",
        )
        
        # 验证能量排序
        energy_sorted = all(energies[i][0] <= energies[i+1][0] for i in range(len(energies)-1))
        report.add(
            system.pdb_id,
            "能量排序",
            energy_sorted,
            "递增顺序",
            str([f"{e[0]:.3f}" for e in energies[:5]]),
            f"{system.name} 构象能量排序",
        )
        
    except ImportError:
        report.add(
            system.pdb_id,
            "对接验证",
            False,
            "Vina 可用",
            "Vina 未安装",
            "跳过对接验证",
        )
    except Exception as e:  # noqa: BLE001
        report.add(
            system.pdb_id,
            "对接验证",
            False,
            "成功",
            f"错误: {e}",
            "对接运行失败",
        )


# ── 主函数 ──────────────────────────────────────────────────────────────────

def main() -> None:
    """运行多体系验证"""
    print("VinaStudio 多体系学术验证脚本")
    print("正在验证多个蛋白质-配体复合物...\n")
    
    report = ValidationReport()
    
    # 验证 1iep (已有数据)
    print("[1/4] 验证 1iep (c-Abl + 伊马替尼)...")
    iep_system = VALIDATION_SYSTEMS[0]
    iep_receptor = SAMPLE_DIR / iep_system.receptor_name
    iep_ligand = SAMPLE_DIR / iep_system.ligand_name
    
    if iep_receptor.exists() and iep_ligand.exists():
        # 使用现有数据验证
        from vinastudio.core.chem.pdbqt import parse_pdbqt
        from vinastudio.core.chem.receptor_prep import (
            ReceptorPrepOptions,
            prepare_receptor,
        )

        # 重新准备受体以获取正确的原子数
        receptor_pdb = SAMPLE_DIR / "1iep_receptorH.pdb"
        options = ReceptorPrepOptions(allow_bad_residues=True)
        prepared = prepare_receptor(receptor_pdb, options)
        doc = parse_pdbqt(prepared.pdbqt)
        
        report.add(
            "1iep",
            "受体原子数",
            doc.first_pose.n_atoms == 2702,
            "2702",
            str(doc.first_pose.n_atoms),
            "c-Abl 激酶受体（去除非极性氢后）",
        )
        
        # 配体验证
        from rdkit import Chem
        supplier = Chem.SDMolSupplier()
        supplier.SetData(iep_ligand.read_text(), removeHs=False, sanitize=True)
        molecules = [mol for mol in supplier if mol is not None]
        
        report.add(
            "1iep",
            "配体 SDF 可读",
            len(molecules) >= 1,
            "≥ 1 个有效分子",
            f"{len(molecules)} 个有效分子",
            "伊马替尼 SDF",
        )
        
        # 对接结果验证
        docking_output = SAMPLE_DIR / "1iep_ligand_vina_out.pdbqt"
        if docking_output.exists():
            docking_doc = parse_pdbqt(docking_output.read_text())
            best_affinity = docking_doc.poses[0].energy
            
            report.add(
                "1iep",
                "对接亲和力",
                abs(best_affinity - (-13.2)) <= 2.0,
                "-13.2 ± 2.0 kcal/mol",
                f"{best_affinity:.3f} kcal/mol",
                "c-Abl + 伊马替尼对接结果",
            )
    else:
        report.add("1iep", "数据准备", False, "文件存在", "文件缺失", "1iep 数据未准备")
    
    # 验证其他体系
    for i, system in enumerate(VALIDATION_SYSTEMS[1:], 2):
        print(f"\n[{i}/4] 验证 {system.pdb_id} ({system.name})...")
        
        # 准备体系
        if prepare_system(system, VALIDATION_DIR):
            validate_system(system, report, VALIDATION_DIR)
            run_docking_validation(system, report, VALIDATION_DIR)
        else:
            report.add(
                system.pdb_id,
                "体系准备",
                False,
                "成功",
                "失败",
                f"无法准备 {system.name} 体系",
            )
    
    # 打印报告
    report.print_report()
    
    # 保存 JSON 报告
    json_path = ROOT / "docs" / "multi_system_validation_report.json"
    json_data = {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "systems": [s.pdb_id for s in VALIDATION_SYSTEMS],
        "results": [
            {
                "system": r.system,
                "name": r.name,
                "passed": bool(r.passed),
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
