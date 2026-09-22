"""Spawned child process that runs Vina docking and reports progress.

The worker receives parameters as a pickle-able dict through
``multiprocessing.Process``, redirects stdout to capture Vina's progress, and
sends structured events through a ``multiprocessing.Connection`` pipe back to
the parent's reader thread.

Vina's stdout when ``verbosity >= 1`` follows this pattern::

    Computing Vina grid ...
    done.
    Performing docking (random seed: 20260920) ...
    0% .. 10% .. 20% .. 30% .. 40% .. 50% .. 60% .. 70% .. 80% .. 90% .. 100%
    -----+------------+----------+----------

The reader thread parses these for stage transitions and percentage updates.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import time
from multiprocessing.connection import Connection
from typing import Any

log = logging.getLogger(__name__)

# Regex patterns for parsing Vina stdout
_GRID_RE = re.compile(r"Computing Vina grid")
_DOCKING_RE = re.compile(r"Performing docking")
_PROGRESS_RE = re.compile(r"(\d+)%")
_RESULTS_RE = re.compile(r"mode\s*\|\s*affinity")


def _emit(pipe: Connection, kind: str, data: dict[str, Any] | None = None) -> None:
    """Send a structured event through the pipe."""
    event: dict[str, Any] = {"type": kind}
    if data:
        event.update(data)
    with contextlib.suppress(BrokenPipeError, OSError):
        pipe.send(event)


def _read_and_parse(pipe: Connection, fd: int) -> None:
    """Read from a file descriptor line-by-line and emit progress events."""
    import fcntl

    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    buffer = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line_bytes, buffer = buffer.split(b"\n", 1)
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                if _GRID_RE.search(line):
                    _emit(pipe, "stage", {"stage": "computing_grid"})
                elif _DOCKING_RE.search(line):
                    _emit(pipe, "stage", {"stage": "docking"})
                elif _RESULTS_RE.search(line):
                    _emit(pipe, "stage", {"stage": "exporting"})
                else:
                    match = _PROGRESS_RE.search(line)
                    if match:
                        _emit(pipe, "progress", {"percent": int(match.group(1))})
                    _emit(pipe, "log", {"line": line})
        except BlockingIOError:
            time.sleep(0.05)
        except (OSError, ValueError):
            break


def docking_worker(params: dict[str, Any], pipe: Connection) -> None:
    """Entry point for the spawned child process.

    Parameters
    ----------
    params : dict
        Pickle-able dict with keys matching :class:`DockingParams` fields,
        plus ``output_dir`` and ``job_id``.
    pipe : Connection
        A ``multiprocessing.Connection`` to send structured events to the parent.
    """
    params.pop("job_id", "unknown")
    output_dir = params.pop("output_dir", "")

    # Redirect stdout so Vina's progress lines flow through our parser.
    read_fd, write_fd = os.pipe()
    old_stdout = os.dup(1)
    os.dup2(write_fd, 1)
    os.close(write_fd)

    # Start a reader thread that parses stdout asynchronously.
    import threading

    reader = threading.Thread(target=_read_and_parse, args=(pipe, read_fd), daemon=True)
    reader.start()

    _emit(pipe, "stage", {"stage": "initialising"})

    try:
        from vinastudio.core.docking import DockingParams, run_docking

        docking_params = DockingParams(**params)
        result = run_docking(docking_params, output_dir)

        _emit(pipe, "completed", {
            "poses": [{"index": p.index, "affinity": p.affinity,
                        "rmsdLower": p.rmsd_lower, "rmsdUpper": p.rmsd_upper}
                       for p in result.poses],
            "bestAffinity": result.best_affinity,
            "nPoses": result.n_poses,
            "elapsedMs": result.elapsed_ms,
            "posesPdbqt": result.poses_pdbqt,
            "posesSdf": result.poses_sdf,
        })
    except Exception as exc:
        log.exception("docking worker failed")
        _emit(pipe, "failed", {"error": str(exc)})
    finally:
        # Restore stdout first: that closes the pipe's write end, so the reader
        # sees EOF and returns.  Joining before that point always burned the
        # full timeout — the write end was still open — and then raced the
        # reader against ``os.close(read_fd)``.
        os.dup2(old_stdout, 1)
        os.close(old_stdout)
        reader.join(timeout=2.0)
        os.close(read_fd)
        pipe.close()


def batch_docking_worker(params: dict[str, Any], pipe: Connection) -> None:
    """Entry point for a batch docking child process.

    Iterates over ligands, docking each one and reporting progress.  Every
    ligand writes into its own subdirectory of ``output_dir`` so the poses
    survive the run: results on disk are what the job's artifacts point at.
    """
    from pathlib import Path

    from vinastudio.core.paths import slugify

    params.pop("job_id", "unknown")
    output_dir = params.pop("output_dir", "")
    ligands = params.pop("ligands", [])
    started = time.monotonic()

    _emit(pipe, "stage", {"stage": "initialising", "totalLigands": len(ligands)})

    results: list[dict[str, Any]] = []
    completed = 0
    failed = 0

    for idx, lig in enumerate(ligands):
        ligand_path = lig.get("ligandPath")
        ligand_string = lig.get("ligandPdbqtString")
        label = lig.get("label", f"ligand_{idx}")
        out_name = f"{idx:03d}-{slugify(label, fallback=f'ligand-{idx}')}"

        _emit(pipe, "batch_progress", {
            "ligandIndex": idx,
            "label": label,
            "status": "running",
            "completed": completed,
            "failed": failed,
            "total": len(ligands),
        })

        if not ligand_path and not ligand_string:
            results.append({
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": "either ligandPath or ligandPdbqtString must be provided",
            })
            failed += 1
            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": "either ligandPath or ligandPdbqtString must be provided",
                "completed": completed,
                "failed": failed,
                "total": len(ligands),
            })
            continue

        try:
            from vinastudio.core.docking import DockingParams, run_docking

            docking_params = DockingParams(
                receptor_path=params.get("receptor_path", ""),
                flex_pdbqt_path=params.get("flex_pdbqt_path"),
                ligand_path=ligand_path,
                ligand_pdbqt_string=ligand_string,
                center=params.get("center", [0, 0, 0]),
                size=params.get("size", [20, 20, 20]),
                scoring=params.get("scoring", "vina"),
                exhaustiveness=params.get("exhaustiveness", 8),
                n_poses=params.get("n_poses", 20),
                energy_range=params.get("energy_range", 3.0),
                min_rmsd=params.get("min_rmsd", 1.0),
                cpu=params.get("cpu", 0),
                seed=params.get("seed", 0),
                no_refine=params.get("no_refine", False),
            )

            run_dir = Path(output_dir) / out_name if output_dir else Path(out_name)
            run_dir.mkdir(parents=True, exist_ok=True)
            result = run_docking(docking_params, str(run_dir))

            best = min((p.affinity for p in result.poses), default=0.0) if result.poses else 0.0
            results.append({
                "ligandIndex": idx,
                "label": label,
                "status": "completed",
                "bestAffinity": best,
                "nPoses": result.n_poses,
                "elapsedMs": result.elapsed_ms,
                "outDir": out_name,
                "pdbqt": result.poses_pdbqt,
            })
            completed += 1

            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "completed",
                "bestAffinity": best,
                "nPoses": result.n_poses,
                "elapsedMs": result.elapsed_ms,
                "outDir": out_name,
                "completed": completed,
                "failed": failed,
                "total": len(ligands),
            })

        except Exception as exc:
            log.exception("batch docking failed for ligand %d", idx)
            results.append({
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": str(exc),
            })
            failed += 1

            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": str(exc),
                "completed": completed,
                "failed": failed,
                "total": len(ligands),
            })

    _emit(pipe, "completed", {
        "results": results,
        "total": len(ligands),
        "completed": completed,
        "failed": failed,
        "elapsedMs": int((time.monotonic() - started) * 1000),
    })
