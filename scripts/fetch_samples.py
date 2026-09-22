"""Download the 1iep reference example used as the project's gold standard.

The files come from the AutoDock Vina repository's ``basic_docking`` tutorial
(Apache-2.0) and are the same ones the upstream documentation uses, so the
binding affinity this project reproduces can be compared against a published
number: c-Abl with imatinib, best pose around -13 kcal/mol with the Vina force
field when docking into a 20 A box centred on (15.190, 53.903, 16.917).

Checksums are pinned so a changed upstream file is detected rather than
silently altering the reference result.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "vinastudio" / "resources" / "sample" / "1iep"

_RAW = "https://raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/develop/example"
_TIMEOUT = 60
_ATTEMPTS = 3


@dataclass(frozen=True)
class Sample:
    filename: str
    url: str
    sha256: str
    description: str


SAMPLES: tuple[Sample, ...] = (
    Sample(
        "1iep_receptorH.pdb",
        f"{_RAW}/basic_docking/data/1iep_receptorH.pdb",
        "5f6aee6029f9a2a2c2be32d4eb948ae70808690573e1b69a0850cdffd7048ca7",
        "c-Abl kinase domain, protonated; the documented preparation input",
    ),
    Sample(
        "1iep_ligand.sdf",
        f"{_RAW}/basic_docking/data/1iep_ligand.sdf",
        "051b8742c32adc05c07fb486a4e7c9327f84e131cee33ac4e6a568d07553eb38",
        "imatinib with hydrogens and 3D coordinates",
    ),
    Sample(
        "1iep_ligand.pdbqt",
        f"{_RAW}/basic_docking/solution/1iep_ligand.pdbqt",
        "15fb35648d8c18c70317842f3a0631b73a19429c710a037ab07310084d579bb8",
        "imatinib prepared by Meeko, as fed to Vina",
    ),
    Sample(
        "1iep_ligand_vina_out.pdbqt",
        f"{_RAW}/basic_docking/solution/1iep_ligand_vina_out.pdbqt",
        "4137e1960b3491f17a24579d991f32a2c0cb254af1f58d7278f77579fc27d93f",
        "four docked poses with Vina affinities, for parser and export tests",
    ),
    Sample(
        "1iep_receptor.pdbqt",
        f"{_RAW}/python_scripting/1iep_receptor.pdbqt",
        "761469710e3915b89b274483076dfe49754be7956661bc42f4cc36a182399d59",
        "receptor PDBQT produced by upstream Meeko, for comparison",
    ),
)

log = logging.getLogger("fetch_samples")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:
                payload = response.read()
            if not payload:
                raise OSError("empty response")
            target.write_bytes(payload)
            return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
            log.warning("attempt %d/%d for %s failed: %s", attempt, _ATTEMPTS, url, exc)
    raise SystemExit(f"could not download {url}: {last_error}")


def fetch(force: bool = False) -> int:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for sample in SAMPLES:
        target = SAMPLE_DIR / sample.filename
        if target.exists() and not force:
            actual = sha256_of(target)
            status = "ok" if actual == sample.sha256 else "CHECKSUM MISMATCH"
            log.info("%-32s present (%s)", sample.filename, status)
            failures += actual != sample.sha256
            continue

        log.info("downloading %s ...", sample.filename)
        _download(sample.url, target)
        actual = sha256_of(target)
        if actual != sample.sha256:
            log.error("%s checksum mismatch: %s", sample.filename, actual)
            failures += 1
        else:
            log.info("  %s verified (%d bytes)", sample.filename, target.stat().st_size)

    if failures:
        log.error("%d sample(s) are not in the expected state", failures)
        return 1
    log.info("samples ready in %s", SAMPLE_DIR)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-download existing files.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return fetch(force=args.force)


if __name__ == "__main__":
    sys.exit(main())
