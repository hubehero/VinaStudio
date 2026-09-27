"""Offline self-contained HTML report for a docking run.

Why string templates: the report must double-click open from disk with zero
network access, and a template engine would add a dependency for exactly one
page. Why the aggressive escaping: labels and paths are user-controlled text
and a shared report leaves the app's trust boundary — one unescaped ``<`` in a
ligand name would otherwise become markup in the reader's browser.
"""

from __future__ import annotations

import html
import re
from typing import Any

from vinastudio.core.chem.pose_validation import THRESHOLDS

#: Anything in an inlined diagram that could execute or fetch when the
#: standalone report is opened. Rejected upstream; re-checked here so a future
#: caller cannot skip validation by importing this module directly.
_UNSAFE_SVG = re.compile(r"<script|<foreignobject|on\w+\s*=|javascript:", re.I)

_STRINGS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "title": "对接结果报告",
        "generated": "生成时间",
        "system": "体系信息",
        "params": "对接参数",
        "poses": "构象表",
        "svg_caption": "2D 相互作用图",
        "thresholds_heading": "构象校验阈值说明",
        "threshold_note": (
            "下表为本应用构象校验所用几何阈值，供解读结果时参考；"
            "本报告生成时未运行构象校验，构象表不含校验标记。"
        ),
        "disclaimer": (
            "免责声明：本报告中的对接结果为计算预测，仅供候选分子初筛参考，"
            "不构成实验结合活性结论；不同打分函数所得能量不可直接比较。"
        ),
        "job_id": "任务 ID",
        "label": "标签",
        "status": "状态",
        "created": "创建时间",
        "elapsed": "耗时",
        "scoring": "打分函数",
        "pose": "构象",
        "affinity": "亲和力 (kcal/mol)",
        "rmsd_lb": "RMSD 下界 (Å)",
        "rmsd_ub": "RMSD 上界 (Å)",
        "thresholds": {
            "internal_clash": "内部冲突（vdW 半径和的比例）",
            "bond_length": "键长偏差 (Å)",
            "angle": "键角偏差 (°)",
            "planarity": "平面性 RMSD (Å)",
            "out_of_box": "超出盒子 (Å)",
        },
        "threshold_name": "阈值",
        "threshold_value": "取值",
        "untitled": "（未命名）",
        "empty_poses": "（本任务没有构象记录）",
    },
    "en-US": {
        "title": "Docking Results Report",
        "generated": "Generated",
        "system": "System",
        "params": "Docking parameters",
        "poses": "Pose table",
        "svg_caption": "2D interaction diagram",
        "thresholds_heading": "Pose validation thresholds",
        "threshold_note": (
            "The table lists the geometric thresholds this application uses for "
            "pose validation. Validation was not run when this report was "
            "generated, so the pose table carries no validation marks."
        ),
        "disclaimer": (
            "Disclaimer: the docking results in this report are computational "
            "predictions for early screening only; they do not constitute an "
            "experimental binding conclusion. Energies from different scoring "
            "functions are not directly comparable."
        ),
        "job_id": "Job ID",
        "label": "Label",
        "status": "Status",
        "created": "Created",
        "elapsed": "Elapsed",
        "scoring": "Scoring function",
        "pose": "Pose",
        "affinity": "Affinity (kcal/mol)",
        "rmsd_lb": "RMSD lower (Å)",
        "rmsd_ub": "RMSD upper (Å)",
        "thresholds": {
            "internal_clash": "Internal clash (fraction of vdW radii sum)",
            "bond_length": "Bond length deviation (Å)",
            "angle": "Bond angle deviation (°)",
            "planarity": "Planarity RMSD (Å)",
            "out_of_box": "Outside the box (Å)",
        },
        "threshold_name": "Threshold",
        "threshold_value": "Value",
        "untitled": "(untitled)",
        "empty_poses": "(no pose records for this job)",
    },
}

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 2rem auto; max-width: 60rem; padding: 0 1rem; line-height: 1.55; }
h1 { font-size: 1.5rem; margin-bottom: .2rem; }
h2 { font-size: 1.1rem; margin-top: 1.8rem; border-bottom: 1px solid #8884;
     padding-bottom: .25rem; }
.meta { color: #666; font-size: .85rem; margin-top: 0; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th, td { border: 1px solid #8884; padding: .35rem .6rem; text-align: left; }
th { background: #8881; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kv th { width: 12rem; }
svg.interaction { max-width: 100%; height: auto; background: #fff; border: 1px solid #8884; }
.caption { font-size: .85rem; color: #666; }
.disclaimer { margin-top: 2rem; padding: .8rem 1rem; border: 1px solid #8884;
              border-left: 4px solid #c0a050; font-size: .88rem; }
@media print { body { margin: 0; } }
"""


def svg_is_safe(svg: str) -> bool:
    """Whether an inlined diagram can be embedded without script risk."""
    return _UNSAFE_SVG.search(svg) is None


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_number(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}"
    return "" if value is None else str(value)


def _fmt_param(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}={val}" for key, val in sorted(value.items()))
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _kv_rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f"<tr><th>{_esc(key)}</th><td>{_esc(value)}</td></tr>" for key, value in pairs
    )


def render_report(
    *,
    lang: str,
    job_id: str,
    label: str,
    status: str,
    created: str,
    elapsed: str | None,
    scoring: str,
    params: dict[str, Any],
    poses: list[dict[str, Any]],
    svg: str | None,
) -> str:
    """Render the one-page report. ``svg`` must already pass ``svg_is_safe``."""
    strings = _STRINGS.get(lang, _STRINGS["zh-CN"])
    display_label = label or strings["untitled"]

    system_rows = _kv_rows(
        [
            (strings["job_id"], job_id),
            (strings["label"], display_label),
            (strings["status"], status),
            (strings["created"], created),
            (strings["elapsed"], elapsed or ""),
            (strings["scoring"], scoring),
        ]
    )

    param_rows = _kv_rows(
        [
            (key, _fmt_param(value))
            for key, value in sorted(params.items())
            if value is not None and value != "" and value != []
        ]
    )

    if poses:
        body = "".join(
            "<tr>"
            f"<td class=\"num\">{_esc(pose.get('index', i))}</td>"
            f"<td class=\"num\">{_esc(_fmt_number(pose.get('affinity')))}</td>"
            f"<td class=\"num\">{_esc(_fmt_number(pose.get('rmsdLower')))}</td>"
            f"<td class=\"num\">{_esc(_fmt_number(pose.get('rmsdUpper')))}</td>"
            "</tr>"
            for i, pose in enumerate(poses, start=1)
        )
        pose_table = (
            "<table><thead><tr>"
            f"<th class=\"num\">{_esc(strings['pose'])}</th>"
            f"<th class=\"num\">{_esc(strings['affinity'])}</th>"
            f"<th class=\"num\">{_esc(strings['rmsd_lb'])}</th>"
            f"<th class=\"num\">{_esc(strings['rmsd_ub'])}</th>"
            "</tr></thead>"
            f"<tbody id=\"poses-body\">{body}</tbody></table>"
        )
    else:
        pose_table = f"<p>{_esc(strings['empty_poses'])}</p>"

    svg_section = ""
    if svg and svg_is_safe(svg):
        svg_section = (
            "<section id=\"interaction\">"
            f"<h2>{_esc(strings['svg_caption'])}</h2>"
            f"{svg}"
            f"<p class=\"caption\">{_esc(strings['svg_caption'])}</p>"
            "</section>"
        )

    threshold_labels: dict[str, str] = strings["thresholds"]  # type: ignore[assignment]
    threshold_rows = "".join(
        f"<tr><th>{_esc(threshold_labels.get(key, key))}</th>"
        f"<td class=\"num\">{_esc(value)}</td></tr>"
        for key, value in THRESHOLDS.items()
    )

    return (
        "<!DOCTYPE html>\n"
        f"<html lang=\"{_esc(lang)}\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_esc(strings['title'])} — {_esc(display_label)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{_esc(strings['title'])}</h1>\n"
        f"<p class=\"meta\">{_esc(strings['generated'])}: {_esc(created)}</p>\n"
        f"<section id=\"system\"><h2>{_esc(strings['system'])}</h2>"
        f"<table class=\"kv\"><tbody>{system_rows}</tbody></table></section>\n"
        f"<section id=\"params\"><h2>{_esc(strings['params'])}</h2>"
        f"<table class=\"kv\"><tbody>{param_rows}</tbody></table></section>\n"
        f"<section id=\"poses\"><h2>{_esc(strings['poses'])}</h2>{pose_table}</section>\n"
        f"{svg_section}\n"
        f"<section id=\"thresholds\"><h2>{_esc(strings['thresholds_heading'])}</h2>"
        f"<p class=\"caption\">{_esc(strings['threshold_note'])}</p>"
        f"<table><thead><tr><th>{_esc(strings['threshold_name'])}</th>"
        f"<th class=\"num\">{_esc(strings['threshold_value'])}</th></tr></thead>"
        f"<tbody>{threshold_rows}</tbody></table></section>\n"
        f"<footer class=\"disclaimer\">{_esc(strings['disclaimer'])}</footer>\n"
        "</body>\n</html>\n"
    )
