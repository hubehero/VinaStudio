"""Reference data must be what the project says it is.

`scripts/fetch_samples.py` is the single description of the 1iep gold standard:
file name, source URL and SHA-256.  The files are also committed so the suite
runs offline, which is what these tests keep honest — a replaced, truncated or
failed download fails here rather than quietly changing the reference result.

The extra validation set under `sample/` is not committed, so its checks skip
when the directory is absent.  They caught two 404 error pages saved as ligand
files and a batch file whose bond count did not match its own header.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from scripts.fetch_samples import Sample

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_samples import SAMPLE_DIR, SAMPLES  # noqa: E402

SAMPLE_SET = REPO_ROOT / "sample"
requires_sample_set = pytest.mark.skipif(
    not SAMPLE_SET.is_dir(),
    reason="the extra validation sample set is not present (see sample/README.md)",
)

#: HEM is the deposited RCSB definition; RDKit cannot sanitise the porphyrin's
#: charge representation even though the file is structurally sound.
UNSANITISABLE = {"4hhb_ligand.sdf"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda sample: sample.filename)
def test_committed_reference_file_matches_its_checksum(sample: Sample) -> None:
    path = SAMPLE_DIR / sample.filename
    assert path.exists(), f"{sample.filename} is missing; run scripts/fetch_samples.py"
    assert _sha256(path) == sample.sha256


@requires_sample_set
def test_sample_set_contains_no_download_error_pages() -> None:
    for path in sorted(SAMPLE_SET.rglob("*")):
        if not path.is_file():
            continue
        head = path.read_text(encoding="utf-8", errors="replace")[:200].lstrip()
        assert not head.lower().startswith(("<!doctype", "<html")), (
            f"{path.relative_to(REPO_ROOT)} is an HTML page, not molecular data"
        )


@requires_sample_set
def test_sample_set_ligands_parse() -> None:
    from rdkit import Chem

    ligand_dir = SAMPLE_SET / "ligands"
    assert ligand_dir.is_dir()

    for path in sorted(ligand_dir.iterdir()):
        sanitize = path.name not in UNSANITISABLE
        if path.suffix == ".sdf":
            mols = [
                mol
                for mol in Chem.SDMolSupplier(str(path), removeHs=False, sanitize=sanitize)
                if mol is not None
            ]
        elif path.suffix == ".mol":
            mol = Chem.MolFromMolFile(str(path), removeHs=False, sanitize=sanitize)
            mols = [mol] if mol is not None else []
        elif path.suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False, sanitize=sanitize)
            mols = [mol] if mol is not None else []
        else:
            continue

        assert mols, f"{path.name} contains no readable molecule"

    # The batch sample is the input the documented batch workflow uses; both
    # molecules have to come back.
    batch = ligand_dir / "batch_test.sdf"
    if batch.exists():
        supplier = Chem.SDMolSupplier(str(batch), removeHs=False)
        assert len(supplier) == 2
        assert all(mol is not None for mol in supplier)


@requires_sample_set
def test_sample_set_receptors_contain_coordinates() -> None:
    import gemmi

    receptor_dir = SAMPLE_SET / "receptors"
    assert receptor_dir.is_dir()

    for path in sorted(receptor_dir.iterdir()):
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".pdb":
            assert any(line.startswith(("ATOM", "HETATM")) for line in text.splitlines()), (
                f"{path.name} has no coordinate records"
            )
        elif path.suffix in {".cif", ".mmcif"}:
            structure = gemmi.read_structure_string(text, format=gemmi.CoorFormat.Mmcif)
            assert len(structure) > 0, f"{path.name} parsed to no models"
