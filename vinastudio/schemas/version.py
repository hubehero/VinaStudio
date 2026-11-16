"""Schema-version rules shared by the headless contracts.

The result is an output: a 1.x reader accepts newer minor versions and ignores
unknown fields. Job and screen are user-authored inputs: they stay strict so a
typo is an error, and the supported minor is exact. A 2.0 contract always needs
a new reader.
"""

from __future__ import annotations

SUPPORTED_MAJOR = 1
SUPPORTED_MINOR = 0

#: ``job.json`` and ``screen.json`` require this exact version.
INPUT_VERSION_PATTERN = rf"^{SUPPORTED_MAJOR}\.{SUPPORTED_MINOR}$"

#: ``result.json`` readers accept any newer 1.x minor.
OUTPUT_VERSION_PATTERN = rf"^{SUPPORTED_MAJOR}\.\d+$"


def _version_text(value: object, contract: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{contract} schemaVersion must be a string")
    return value


def validate_input_version(value: object, contract: str) -> str:
    """Require the exact supported minor for a user-authored input."""
    text = _version_text(value, contract)
    current = f"{SUPPORTED_MAJOR}.{SUPPORTED_MINOR}"
    if text == current:
        return text
    if text.startswith(f"{SUPPORTED_MAJOR}."):
        raise ValueError(
            f"{contract} schemaVersion {text!r} is newer than the supported "
            f"{current}; upgrade VinaStudio"
        )
    raise ValueError(
        f"{contract} schemaVersion {text!r} is not supported; "
        f"this build reads {SUPPORTED_MAJOR}.x"
    )


def validate_output_version(value: object, contract: str) -> str:
    """Accept additive 1.x output while rejecting a new major."""
    text = _version_text(value, contract)
    if text == f"{SUPPORTED_MAJOR}.{SUPPORTED_MINOR}":
        return text
    prefix = f"{SUPPORTED_MAJOR}."
    if text.startswith(prefix) and text[len(prefix) :].isdigit():
        return text
    raise ValueError(
        f"{contract} schemaVersion {text!r} is not supported; "
        f"this build reads {SUPPORTED_MAJOR}.x outputs"
    )
