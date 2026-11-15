"""CLI exit codes and exception mapping."""

from __future__ import annotations

from vinastudio.core.errors import (
    EngineCapabilityError,
    InvalidInputError,
    PreparationError,
    VinaStudioError,
)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INPUT = 2
EXIT_ENGINE = 3
EXIT_CANCELLED = 4


class CliError(Exception):
    exit_code = EXIT_FAILURE
    code = "failure"


class InputError(CliError):
    exit_code = EXIT_INPUT
    code = "invalid_input"


class EngineError(CliError):
    exit_code = EXIT_ENGINE
    code = "engine_unavailable"


class Cancelled(CliError):
    exit_code = EXIT_CANCELLED
    code = "cancelled"


def classify(exc: BaseException) -> CliError:
    """Map domain failures onto the documented CLI exit codes."""
    if isinstance(exc, CliError):
        return exc
    if isinstance(exc, KeyboardInterrupt):
        return Cancelled("cancelled")
    if isinstance(exc, EngineCapabilityError):
        return EngineError(str(exc))
    if isinstance(exc, (InvalidInputError, PreparationError, FileNotFoundError, ValueError)):
        return InputError(str(exc))
    if isinstance(exc, VinaStudioError) and exc.status_code in {409, 503}:
        return EngineError(str(exc))
    return CliError(str(exc) or type(exc).__name__)
