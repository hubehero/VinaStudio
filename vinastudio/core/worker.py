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
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from vinastudio.core.engines.common import events_for_line

log = logging.getLogger(__name__)


def _emit(pipe: Connection, kind: str, data: dict[str, Any] | None = None) -> None:
    """Send a structured event through the pipe."""
    event: dict[str, Any] = {"type": kind}
    if data:
        event.update(data)
    with contextlib.suppress(BrokenPipeError, OSError):
        pipe.send(event)


def _read_and_parse(pipe: Connection, fd: int) -> None:
    """Read Vina's stdout line-by-line and emit progress events.

    Blocking reads, in the thread that exists for exactly this: the write end is
    closed when the worker restores stdout, so the loop ends at EOF. The previous
    version flipped the descriptor to non-blocking mode with ``fcntl`` — a
    POSIX-only module, which made this worker unimportable on Windows — and the
    only thing that bought was a 50 ms poll loop. A worker that wedges anyway is
    killed by the parent, and this thread dies with the process.
    """
    buffer = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
        except (OSError, ValueError):
            break
        if not chunk:
            break

        buffer += chunk
        while b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            line = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            for kind, data in events_for_line(line):
                _emit(pipe, kind, data)


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
    """Entry point for one shard of a batch docking job.

    The parent splits the ligand list statically (``ligands[i::N]``) and
    starts one of these per shard; each docks its own slice while keeping the
    original ligand index for events and on-disk names.  Every ligand writes
    into its own subdirectory of ``output_dir`` so the poses survive the run:
    results on disk are what the job's artifacts point at.  The shared Vina
    maps were pre-computed by the parent and arrive as ``map_prefix``;
    without it (precompute failed / ad4 / external maps) every ligand
    computes its own, as before.

    Progress is reported as per-ligand facts only — job-level counters and
    the completion event belong to the parent (TASK-14 §4.3).
    """
    from pathlib import Path

    from vinastudio.core.paths import slugify

    params.pop("job_id", "unknown")
    output_dir = params.pop("output_dir", "")
    ligands = params.pop("ligands", [])
    shard_index = int(params.pop("shard_index", 0))
    shard_count = max(1, int(params.pop("shard_count", 1)))

    _emit(pipe, "stage", {"stage": "initialising", "totalLigands": len(ligands)})

    scoring = params.get("scoring", "vina")
    map_prefix: str = str(params.get("map_prefix") or "")
    if map_prefix:
        _emit(pipe, "stage", {"stage": "docking"})

    shard = list(enumerate(ligands))[shard_index::shard_count]

    for idx, lig in shard:
        ligand_path = lig.get("ligandPath")
        ligand_string = lig.get("ligandPdbqtString")
        label = lig.get("label", f"ligand_{idx}")
        out_name = f"{idx:03d}-{slugify(label, fallback=f'ligand-{idx}')}"

        _emit(pipe, "batch_progress", {
            "ligandIndex": idx,
            "label": label,
            "status": "running",
        })

        # Descriptors are computed at entry start so every outcome — including
        # the failed rows below — carries them (TASK-13 §4.6); best effort,
        # nulls when nothing parses, never blocking the docking itself.
        from vinastudio.core.chem.properties import ligand_profile

        profile = ligand_profile(ligand_path, pdbqt_path=ligand_path, pdbqt_text=ligand_string)
        desc_fields = {
            "qed": profile["qed"],
            "lipinskiViolations": profile["lipinskiViolations"],
            "smiles": profile["smiles"],
        }

        if not ligand_path and not ligand_string:
            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": "either ligandPath or ligandPdbqtString must be provided",
                **desc_fields,
            })
            continue

        try:
            from vinastudio.core.docking import DockingParams, run_docking

            # N shards are the parallel budget; letting each also take a
            # full CPU's threads would oversubscribe the machine N-fold
            # (TASK-14 §4.1).  A lone shard keeps the request's cpu
            # semantics — including 0 = every core — untouched.
            cpu = 1 if shard_count > 1 else params.get("cpu", 0)
            docking_params = DockingParams(
                receptor_path=params.get("receptor_path", ""),
                flex_pdbqt_path=params.get("flex_pdbqt_path"),
                ligand_path=ligand_path,
                ligand_pdbqt_string=ligand_string,
                center=tuple(params.get("center", [0, 0, 0])),
                size=tuple(params.get("size", [20, 20, 20])),
                scoring=scoring,
                exhaustiveness=params.get("exhaustiveness", 8),
                n_poses=params.get("n_poses", 20),
                energy_range=params.get("energy_range", 3.0),
                min_rmsd=params.get("min_rmsd", 1.0),
                cpu=cpu,
                seed=params.get("seed", 0),
                no_refine=params.get("no_refine", False),
                map_prefix=map_prefix or None,
                engine=params.get("engine", "vina"),
            )

            run_dir = Path(output_dir) / out_name if output_dir else Path(out_name)
            run_dir.mkdir(parents=True, exist_ok=True)
            result = run_docking(docking_params, str(run_dir))

            best = min((p.affinity for p in result.poses), default=0.0) if result.poses else 0.0
            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "completed",
                "bestAffinity": best,
                "nPoses": result.n_poses,
                "elapsedMs": result.elapsed_ms,
                "outDir": out_name,
                **desc_fields,
            })

        except Exception as exc:
            log.exception("batch docking failed for ligand %d", idx)
            _emit(pipe, "ligand_completed", {
                "ligandIndex": idx,
                "label": label,
                "status": "failed",
                "error": str(exc),
                **desc_fields,
            })

    # No completion event here: the parent emits the job's single
    # `completed` once every shard has exited (TASK-14 §4.3).


def screening_worker(params: dict[str, Any], pipe: Connection) -> None:
    """Entry point for one shard of a virtual screening job (TASK-13 §4.2).

    Mirrors ``batch_docking_worker``'s shard contract, but each entry is a
    library record instead of a ready PDBQT: the prepared file is created
    lazily on the first run (prepare truth is the file on disk; ``index.json``
    is never written by a worker — §4.1).  No shared maps — every ligand
    computes its own (TASK-14 Q1 方案 B; ``load_maps`` would SIGSEGV, §4.2
    勘误①).  ``ligandIndex`` is the library entry index, which is what
    ``screening.jsonl``'s ``i`` and the resume skip set key on.
    """
    from pathlib import Path

    from vinastudio.core.chem.library import (
        clear_prepare_failure,
        entry_pdbqt_path,
        entry_sdf_path,
        mark_prepare_failed,
    )
    from vinastudio.core.chem.properties import ligand_profile
    from vinastudio.core.paths import slugify

    params.pop("job_id", "unknown")
    output_dir = params.pop("output_dir", "")
    entries = params.pop("entries", [])
    libdir = Path(params.pop("library_dir", ""))
    shard_index = int(params.pop("shard_index", 0))
    shard_count = max(1, int(params.pop("shard_count", 1)))

    _emit(pipe, "stage", {"stage": "initialising", "totalLigands": len(entries)})

    scoring = params.get("scoring", "vina")
    shard = list(enumerate(entries))[shard_index::shard_count]

    for position, entry in shard:
        entry_index = int(entry.get("index", position))
        name = str(entry.get("name") or f"mol_{entry_index}")
        sdf = entry_sdf_path(libdir, entry_index)
        pdbqt = entry_pdbqt_path(libdir, entry_index)
        out_name = f"{entry_index:06d}-{slugify(name, fallback=f'mol-{entry_index}')}"

        _emit(pipe, "batch_progress", {
            "ligandIndex": entry_index,
            "label": name,
            "status": "running",
        })

        # Source SDF wins over the prepared file's header SMILES (§4.6);
        # computed at entry start so failed rows carry the fields too.
        profile = ligand_profile(str(sdf), pdbqt_path=str(pdbqt))
        desc_fields = {
            "qed": profile["qed"],
            "lipinskiViolations": profile["lipinskiViolations"],
            "smiles": profile["smiles"],
        }

        try:
            if not pdbqt.is_file():
                from vinastudio.core.chem.ligand_prep import prepare_ligand

                try:
                    prepared = prepare_ligand(str(sdf))
                    pdbqt.write_text(prepared.pdbqt, encoding="utf-8")
                except Exception as exc:
                    mark_prepare_failed(libdir, entry_index, str(exc))
                    raise
            clear_prepare_failure(libdir, entry_index)

            from vinastudio.core.docking import DockingParams, run_docking

            # Same oversubscription rule as the batch shard (TASK-14 §4.1).
            cpu = 1 if shard_count > 1 else params.get("cpu", 0)
            docking_params = DockingParams(
                receptor_path=params.get("receptor_path", ""),
                flex_pdbqt_path=params.get("flex_pdbqt_path"),
                ligand_path=str(pdbqt),
                center=tuple(params.get("center", [0, 0, 0])),
                size=tuple(params.get("size", [20, 20, 20])),
                scoring=scoring,
                exhaustiveness=params.get("exhaustiveness", 8),
                n_poses=params.get("n_poses", 20),
                energy_range=params.get("energy_range", 3.0),
                min_rmsd=params.get("min_rmsd", 1.0),
                cpu=cpu,
                seed=params.get("seed", 0),
                no_refine=params.get("no_refine", False),
                engine=params.get("engine", "vina"),
            )

            run_dir = Path(output_dir) / out_name if output_dir else Path(out_name)
            run_dir.mkdir(parents=True, exist_ok=True)
            result = run_docking(docking_params, str(run_dir))

            best = min((p.affinity for p in result.poses), default=0.0) if result.poses else 0.0
            _emit(pipe, "ligand_completed", {
                "ligandIndex": entry_index,
                "label": name,
                "status": "completed",
                "bestAffinity": best,
                "nPoses": result.n_poses,
                "elapsedMs": result.elapsed_ms,
                "outDir": out_name,
                **desc_fields,
            })
        except Exception as exc:
            log.exception("screening failed for library entry %d", entry_index)
            _emit(pipe, "ligand_completed", {
                "ligandIndex": entry_index,
                "label": name,
                "status": "failed",
                "error": str(exc),
                **desc_fields,
            })

    # No completion event here: the parent emits the job's single
    # `completed` once every shard has exited (TASK-14 §4.3).


def site_screening_worker(params: dict[str, Any], pipe: Connection) -> None:
    """Dock one ligand into each candidate box, one row per box (S2).

    No sharding: the detector hands over a short list of boxes, and keeping them
    in one process keeps the ranking and the "best box" summary in one place.

    The job's terminal event carries the **winning** box's poses, so opening the
    run shows the pose it chose; the per-box rows are the ranking the sites
    endpoint serves. Exhaustiveness is deliberately low by default — this is a
    coarse screen for *choosing a site*, not a production run.
    """
    params.pop("job_id", "unknown")
    output_dir = params.pop("output_dir", "")
    candidates = list(params.get("candidates", []))

    # Vina's progress lines are parsed off stdout, exactly as in the other
    # workers.
    read_fd, write_fd = os.pipe()
    old_stdout = os.dup(1)
    os.dup2(write_fd, 1)
    os.close(write_fd)

    import threading

    reader = threading.Thread(target=_read_and_parse, args=(pipe, read_fd), daemon=True)
    reader.start()

    _emit(pipe, "stage", {"stage": "docking", "totalLigands": len(candidates)})

    best_result = None
    best_affinity: float | None = None
    elapsed_total = 0

    try:
        from vinastudio.core.docking import DockingParams, run_docking

        for position, candidate in enumerate(candidates):
            index = int(candidate.get("index", position))
            label = str(candidate.get("label") or f"candidate-{index}")
            _emit(
                pipe,
                "site_progress",
                {"siteIndex": index, "label": label, "status": "running"},
            )
            try:
                # Vina writes poses into this directory and refuses when it is
                # missing — one directory per candidate keeps the runs apart.
                run_dir = (
                    Path(output_dir) / f"site-{index:03d}"
                    if output_dir
                    else Path(f"site-{index:03d}")
                )
                run_dir.mkdir(parents=True, exist_ok=True)
                result = run_docking(
                    DockingParams(
                        receptor_path=params.get("receptor_path", ""),
                        flex_pdbqt_path=params.get("flex_pdbqt_path"),
                        ligand_path=params.get("ligand_path"),
                        ligand_pdbqt_string=params.get("ligand_pdbqt_string"),
                        center=tuple(candidate.get("center", (0.0, 0.0, 0.0))),
                        size=tuple(candidate.get("size", (20.0, 20.0, 20.0))),
                        scoring=params.get("scoring", "vina"),
                        exhaustiveness=params.get("exhaustiveness", 8),
                        n_poses=params.get("n_poses", 10),
                        energy_range=params.get("energy_range", 3.0),
                        min_rmsd=params.get("min_rmsd", 1.0),
                        max_evals=params.get("max_evals", 0),
                        cpu=params.get("cpu", 0),
                        seed=params.get("seed", 0),
                        no_refine=params.get("no_refine", False),
                        verbosity=params.get("verbosity", 1),
                        spacing=params.get("spacing", 0.375),
                        force_even_voxels=params.get("force_even_voxels", False),
                        weights=params.get("weights"),
                        map_paths=params.get("map_paths"),
                        engine=params.get("engine", "vina"),
                    ),
                    str(run_dir),
                )
            except Exception as exc:  # one bad box must not sink the screen
                log.exception("site screening failed for candidate %d", index)
                _emit(
                    pipe,
                    "site_completed",
                    {"siteIndex": index, "label": label, "status": "failed", "error": str(exc)},
                )
            else:
                affinity = min((pose.affinity for pose in result.poses), default=None)
                elapsed_total += result.elapsed_ms
                if affinity is not None and (
                    best_affinity is None or affinity < best_affinity
                ):
                    best_affinity = affinity
                    best_result = result
                _emit(
                    pipe,
                    "site_completed",
                    {
                        "siteIndex": index,
                        "label": label,
                        "status": "completed",
                        "bestAffinity": affinity,
                        "nPoses": result.n_poses,
                        "elapsedMs": result.elapsed_ms,
                        "outDir": f"site-{index:03d}",
                    },
                )

            _emit(
                pipe,
                "progress",
                {"percent": int((position + 1) / max(1, len(candidates)) * 100)},
            )

        _emit(
            pipe,
            "completed",
            {
                "poses": [
                    {
                        "index": pose.index,
                        "affinity": pose.affinity,
                        "rmsdLower": pose.rmsd_lower,
                        "rmsdUpper": pose.rmsd_upper,
                    }
                    for pose in (best_result.poses if best_result else [])
                ],
                "bestAffinity": best_affinity if best_affinity is not None else 0.0,
                "nPoses": best_result.n_poses if best_result else 0,
                "elapsedMs": elapsed_total,
                "posesPdbqt": best_result.poses_pdbqt if best_result else "",
                "posesSdf": best_result.poses_sdf if best_result else "",
            },
        )
    except Exception as exc:
        log.exception("site screening worker failed")
        _emit(pipe, "failed", {"error": str(exc)})
    finally:
        os.dup2(old_stdout, 1)
        os.close(old_stdout)
        reader.join(timeout=2.0)
        os.close(read_fd)
        pipe.close()
