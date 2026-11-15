"""External engine adapter contract.

An adapter is a JSON manifest plus an executable the user supplies. This module
never downloads or bundles an engine, and it never mixes one engine's scores
with another's: every :class:`EngineResult` carries its own namespace.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vinastudio.core.docking import DockingParams, DockingResult, result_from_poses
from vinastudio.core.errors import EngineCapabilityError, InvalidInputError

CAPABILITIES = frozenset(
    {"dock", "score", "rescore", "optimize", "randomize", "cuda"}
)
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_ALLOWED_PLACEHOLDERS = frozenset(
    {
        "executable",
        "receptor",
        "ligand",
        "out",
        "center_x",
        "center_y",
        "center_z",
        "size_x",
        "size_y",
        "size_z",
        "scoring",
        "exhaustiveness",
        "n_poses",
        "seed",
        "flex",
    }
)


@dataclass(frozen=True, slots=True)
class EngineManifest:
    name: str
    version: str
    license: str
    capabilities: tuple[str, ...]
    executable: str
    command: tuple[str, ...]
    output: str = "poses.pdbqt"
    score_namespace: str = ""
    cancel: str = "process-kill"
    timeout: float = 300.0

    @property
    def namespace(self) -> str:
        return self.score_namespace or self.name

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EngineManifest:
        if not isinstance(payload, dict):
            raise InvalidInputError("engine manifest must be an object")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise InvalidInputError("engine manifest needs a name")
        version = str(payload.get("version") or "").strip()
        licence = str(payload.get("license") or "").strip()
        if not version or not licence:
            raise InvalidInputError(f"engine {name!r} needs version and license")
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise InvalidInputError(f"engine {name!r} needs capabilities")
        if any(not isinstance(item, str) or item not in CAPABILITIES for item in capabilities):
            raise InvalidInputError(
                f"engine {name!r} has an unknown capability; expected {sorted(CAPABILITIES)}"
            )
        executable = str(payload.get("executable") or "").strip()
        command = payload.get("command")
        if not executable or not isinstance(command, list) or not command:
            raise InvalidInputError(f"engine {name!r} needs executable and command")
        if any(not isinstance(part, str) or not part for part in command):
            raise InvalidInputError(f"engine {name!r} command parts must be non-empty strings")
        used = set().union(*(_PLACEHOLDER.findall(part) for part in command))
        unknown = used - _ALLOWED_PLACEHOLDERS
        if unknown:
            raise InvalidInputError(
                f"engine {name!r} command uses unsupported placeholders: {sorted(unknown)}"
            )
        output = str(payload.get("output") or "poses.pdbqt")
        if Path(output).is_absolute() or ".." in Path(output).parts:
            raise InvalidInputError(f"engine {name!r} output must stay inside the run directory")
        cancel = str(payload.get("cancel") or "process-kill")
        if cancel != "process-kill":
            raise InvalidInputError(
                f"engine {name!r} uses unsupported cancel mode {cancel!r}"
            )
        timeout = payload.get("timeout", 300.0)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise InvalidInputError(f"engine {name!r} timeout must be positive")
        return cls(
            name=name,
            version=version,
            license=licence,
            capabilities=tuple(capabilities),
            executable=executable,
            command=tuple(command),
            output=output,
            score_namespace=str(payload.get("scoreNamespace") or ""),
            cancel=cancel,
            timeout=float(timeout),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> EngineManifest:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InvalidInputError(f"could not read engine manifest: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"engine manifest is not valid JSON: {exc}") from exc
        return cls.from_dict(payload)


@dataclass(slots=True)
class EngineResult:
    engine: str
    namespace: str
    result: DockingResult
    stdout: str = ""
    stderr: str = ""


@dataclass(slots=True)
class ExternalEngine:
    manifest: EngineManifest

    def executable_path(self) -> Path:
        candidate = Path(self.manifest.executable).expanduser()
        if candidate.parent != Path(".") or candidate.is_absolute():
            if not candidate.is_file():
                raise EngineCapabilityError(
                    f"engine {self.manifest.name!r} executable not found: {candidate}"
                )
            return candidate
        found = shutil.which(self.manifest.executable)
        if found is None:
            raise EngineCapabilityError(
                f"engine {self.manifest.name!r} executable not found: "
                f"{self.manifest.executable}"
            )
        return Path(found)

    def probe(self) -> dict[str, Any]:
        try:
            executable = self.executable_path()
        except EngineCapabilityError as exc:
            return {
                "name": self.manifest.name,
                "kind": "external",
                "version": self.manifest.version,
                "available": False,
                "reason": str(exc),
                "capabilities": list(self.manifest.capabilities),
                "namespace": self.manifest.namespace,
            }
        return {
            "name": self.manifest.name,
            "kind": "external",
            "version": self.manifest.version,
            "available": executable.is_file(),
            "executable": str(executable),
            "capabilities": list(self.manifest.capabilities),
            "namespace": self.manifest.namespace,
            "license": self.manifest.license,
        }

    def _template_values(
        self, params: DockingParams, output_dir: Path
    ) -> dict[str, str]:
        ligand = params.ligand_path
        if ligand is None:
            ligand_path = output_dir / "ligand.pdbqt"
            ligand_path.write_text(params.ligand_pdbqt_string or "", encoding="utf-8")
            ligand = str(ligand_path)
        values = {
            "executable": str(self.executable_path()),
            "receptor": params.receptor_path,
            "ligand": ligand,
            "out": str(output_dir),
            "center_x": str(params.center[0]),
            "center_y": str(params.center[1]),
            "center_z": str(params.center[2]),
            "size_x": str(params.size[0]),
            "size_y": str(params.size[1]),
            "size_z": str(params.size[2]),
            "scoring": params.scoring,
            "exhaustiveness": str(params.exhaustiveness),
            "n_poses": str(params.n_poses),
            "seed": str(params.seed),
            "flex": params.flex_pdbqt_path or "",
        }
        return values

    def dock(
        self,
        params: DockingParams,
        output_dir: str | Path,
        *,
        timeout: float | None = None,
    ) -> EngineResult:
        if "dock" not in self.manifest.capabilities:
            raise EngineCapabilityError(
                f"engine {self.manifest.name!r} does not advertise dock"
            )
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        values = self._template_values(params, target)
        command = [part.format(**values) for part in self.manifest.command]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout or self.manifest.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"engine {self.manifest.name!r} exceeded its timeout"
            ) from exc
        elapsed = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            raise RuntimeError(
                f"engine {self.manifest.name!r} exited with {completed.returncode}"
                + (f": {detail[-1]}" if detail else "")
            )
        pose_path = target / self.manifest.output
        if not pose_path.is_file():
            raise EngineCapabilityError(
                f"engine {self.manifest.name!r} did not write {self.manifest.output}"
            )
        result = result_from_poses(pose_path, elapsed)
        return EngineResult(
            engine=self.manifest.name,
            namespace=self.manifest.namespace,
            result=result,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


def load_manifests(paths: list[str | Path]) -> list[ExternalEngine]:
    return [ExternalEngine(EngineManifest.from_path(path)) for path in paths]
