"""HTTP contract for the environment diagnostic and safe repair endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DiagnosticSeverity = Literal["ok", "warning", "error"]


class DiagnosticCheck(BaseModel):
    id: str
    severity: DiagnosticSeverity
    fixable: bool = False
    detail: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)


class DiagnosticReport(BaseModel):
    ok: bool
    severity: DiagnosticSeverity
    generatedAt: str
    workspace: str | None
    checks: list[DiagnosticCheck]
    repairAvailable: bool = False
    repaired: list[str] = Field(default_factory=list)
