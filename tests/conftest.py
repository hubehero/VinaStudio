"""Shared pytest fixtures.

The application writes to ``~/.vinastudio`` by default; tests redirect that to a
per-session temporary directory so a test run never touches real user data.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Must happen before anything imports vinastudio.config.
_SESSION_HOME = Path(tempfile.mkdtemp(prefix="vinastudio-tests-"))
os.environ["VINASTUDIO_HOME"] = str(_SESSION_HOME)


@pytest.fixture(scope="session")
def app_home() -> Path:
    return _SESSION_HOME


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    from vinastudio.server.app import create_app

    return create_app()


@pytest.fixture
def client(app) -> Iterator[object]:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
