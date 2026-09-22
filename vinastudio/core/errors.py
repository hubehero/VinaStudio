"""Domain errors that map onto HTTP status codes at the API boundary."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: Longest error summary that may reach an API ``detail`` field.
_MAX_BRIEF_CHARS = 400


class VinaStudioError(Exception):
    """Base class for every error this application raises deliberately."""

    #: HTTP status the API layer should use for this error.
    status_code: int = 500


class InvalidInputError(VinaStudioError):
    """The caller supplied something the pipeline cannot use."""

    status_code = 422


class UnsupportedFormatError(InvalidInputError):
    """The file extension is not one this pipeline accepts."""


class PreparationError(VinaStudioError):
    """Parameterisation failed for a reason the user can act on."""

    status_code = 422


class ReceptorTemplateError(PreparationError):
    """Meeko's residue templates rejected the structure.

    Carries the offending residue identifiers so the interface can offer to
    exclude them and retry instead of just reporting a failure.
    """

    def __init__(self, message: str, residues: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.residues = residues


def brief_error(exc: BaseException | str) -> str:
    """A short, single-sentence summary of a failure, safe for an API message.

    Meeko and friends report failures as multi-line tracebacks that drown the
    one line the user needs.  The full text is logged, never shown: the
    interface has no room for a traceback and the log already keeps it.
    """
    text = str(exc).strip()
    if not text:
        return "unknown error"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # In a traceback the explanatory line is the last one; the rest is frames
    # the user cannot act on.  Otherwise the first line carries the summary.
    is_traceback = "Traceback (most recent call last)" in text
    summary = lines[-1] if is_traceback else lines[0]
    if len(text) > len(summary) or len(summary) > _MAX_BRIEF_CHARS:
        log.warning("error shortened for the interface; full text: %s", text)
    if len(summary) > _MAX_BRIEF_CHARS:
        summary = summary[: _MAX_BRIEF_CHARS - 3].rstrip() + "..."
    return summary


class ExternalServiceError(VinaStudioError):
    """An upstream HTTP service (e.g. RCSB) returned an error or was unreachable."""

    status_code = 502


class JobNotFoundError(VinaStudioError):
    status_code = 404
