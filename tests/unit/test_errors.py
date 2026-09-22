"""API messages must stay one readable line.

Meeko reports failures as multi-line tracebacks; the interface has no room for
those, so :func:`brief_error` reduces them to the one line that explains the
failure and the log keeps the rest.
"""

from __future__ import annotations

from vinastudio.core.errors import brief_error


def test_a_short_plain_message_passes_through() -> None:
    assert brief_error("atom type X is unknown") == "atom type X is unknown"


def test_only_the_first_line_of_a_multi_line_message_is_shown() -> None:
    exc = ValueError("sanitisation failed\nextra detail\nmore detail")
    summary = brief_error(exc)
    assert summary == "sanitisation failed"
    assert "\n" not in summary


def test_a_traceback_reports_the_final_line_not_the_frames() -> None:
    exc = RuntimeError(
        "Traceback (most recent call last):\n"
        '  File "meeko.py", line 1, in <module>\n'
        "    do_the_thing()\n"
        "ValueError: residue A:438 has non-contiguous atoms"
    )
    assert brief_error(exc) == "ValueError: residue A:438 has non-contiguous atoms"


def test_an_enormous_summary_is_truncated_with_an_ellipsis() -> None:
    summary = brief_error("x" * 5000)
    assert len(summary) <= 400
    assert summary.endswith("...")


def test_an_empty_error_still_produces_a_message() -> None:
    assert brief_error("") == "unknown error"
