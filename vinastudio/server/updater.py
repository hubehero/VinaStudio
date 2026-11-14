"""Background update download with checksum verification.

The only network source is the release payload fetched by the update check.
Download URLs must point at GitHub or its release-asset hosts; the downloaded
file is verified against the release's ``SHA256SUMS`` before it is exposed to
the desktop shell.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import certifi

from vinastudio import __version__
from vinastudio.config import APP_NAME, app_home

log = logging.getLogger(__name__)

_ALLOWED_HOSTS = {"github.com", "api.github.com"}
_ALLOWED_SUFFIXES = (".githubusercontent.com",)
_MAX_UPDATE_BYTES = 4 * 1024 * 1024 * 1024
_CHUNK = 1024 * 1024
_CHECKSUM_NAME = "SHA256SUMS"
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.match(value.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _host_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return host in _ALLOWED_HOSTS or host.endswith(_ALLOWED_SUFFIXES)


def _asset_url(asset: dict[str, Any]) -> str | None:
    url = asset.get("browser_download_url")
    if isinstance(url, str) and _host_allowed(url):
        return url
    return None

def _safe_component(value: str) -> bool:
    """Reject path separators in values that become filesystem components."""
    name = Path(value).name
    return bool(value) and name == value and name not in {".", ".."}


def select_update_asset(
    release: dict[str, Any], *, system: str | None = None
) -> dict[str, Any] | None:
    """Choose the installable asset for this OS from a GitHub release payload.

    Windows prefers the Inno Setup executable; Linux prefers the Debian package
    and falls back to the portable archive. macOS has no release package, so it
    deliberately returns ``None`` instead of pretending an archive is an
    installer.
    """
    system = (system or platform.system()).lower()
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    candidates: list[dict[str, Any]] = [
        item for item in assets if isinstance(item, dict) and _asset_url(item)
    ]
    checksum = next(
        (
            item
            for item in candidates
            if str(item.get("name", "")).upper() == _CHECKSUM_NAME
        ),
        None,
    )
    if checksum is None:
        return None
    checksum_url = _asset_url(checksum)
    assert checksum_url is not None

    def choose(predicate) -> dict[str, Any] | None:
        for item in candidates:
            name = str(item.get("name", ""))
            if not _safe_component(name):
                continue
            if predicate(name):
                url = _asset_url(item)
                if url:
                    return {
                        "name": name,
                        "url": url,
                        "checksumUrl": checksum_url,
                        "size": int(item.get("size") or 0),
                        "kind": _install_kind(name, system),
                    }
        return None

    if system.startswith("win"):
        return choose(lambda name: name.lower().endswith(".exe") and "setup" in name.lower())
    if system.startswith("linux"):
        return choose(lambda name: name.lower().endswith(".deb")) or choose(
            lambda name: name.lower().endswith((".tar.gz", ".tgz"))
        )
    return None


def _install_kind(name: str, system: str) -> str:
    lower = name.lower()
    if lower.endswith(".exe"):
        return "windows-installer"
    if lower.endswith(".deb"):
        return "debian-package"
    return "archive"


def parse_sha256sums(text: str, asset_name: str) -> str | None:
    """Return the checksum for ``asset_name`` from a SHA256SUMS file."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0].strip().lower(), parts[-1].lstrip("*")
        if name != asset_name or len(digest) != 64:
            continue
        if all(char in "0123456789abcdef" for char in digest):
            return digest
    return None


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def _fetch_text(url: str, timeout: float = 10.0) -> str:
    if not _host_allowed(url):
        raise ValueError("update URL host is not allowed")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_NAME}/{__version__}", "Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        if not _host_allowed(response.geturl()):
            raise ValueError("update redirect host is not allowed")
        return response.read().decode("utf-8", errors="replace")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _idle_state() -> dict[str, Any]:
    return {
        "state": "idle",
        "version": None,
        "assetName": None,
        "installKind": None,
        "bytes": 0,
        "totalBytes": 0,
        "percent": 0.0,
        "path": None,
        "sha256": None,
        "error": None,
    }


class UpdateDownloadManager:
    """One background download at a time, shared by all HTTP clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = _idle_state()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def _reset(self, **values: Any) -> None:
        self._update(**{**_idle_state(), **values})

    def start(self, release: dict[str, Any]) -> dict[str, Any]:
        latest = str(release.get("tag_name") or "").strip().lstrip("vV")
        current = __version__
        if not _safe_component(latest) or _version_tuple(latest) is None:
            self._reset(state="error", error="invalid_response")
            return self.status()
        if _version_tuple(latest) <= _version_tuple(current):
            self._reset(state="error", error="not_available")
            return self.status()
        asset = select_update_asset(release)
        if asset is None:
            self._reset(
                state="error",
                version=latest,
                error="no_asset",
            )
            return self.status()
        size = int(asset.get("size") or 0)
        if size <= 0 or size > _MAX_UPDATE_BYTES:
            self._reset(
                state="error",
                version=latest,
                assetName=asset["name"],
                error="invalid_asset",
            )
            return self.status()

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(self._state)
            self._cancel.clear()
            self._state = {
                **_idle_state(),
                "state": "starting",
                "version": latest,
                "assetName": asset["name"],
                "installKind": asset["kind"],
                "totalBytes": size,
            }
            thread = threading.Thread(
                target=self._run,
                args=(asset, latest, size),
                name="vinastudio-update-download",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return dict(self._state)

    def error(self, code: str) -> dict[str, Any]:
        self._reset(state="error", error=code)
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._state = {**self._state, "state": "cancelled"}
        return self.status()

    def _fail(self, code: str, part: Path | None = None) -> None:
        if part is not None:
            part.unlink(missing_ok=True)
        self._update(state="error", error=code, path=None)

    def _run(self, asset: dict[str, Any], version: str, total: int) -> None:
        destination = app_home() / "updates" / version / str(asset["name"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(f".{destination.name}.part")
        try:
            checksum_text = _fetch_text(str(asset["checksumUrl"]))
            expected = parse_sha256sums(checksum_text, str(asset["name"]))
            if expected is None:
                self._fail("unverified")
                return
            request = urllib.request.Request(
                str(asset["url"]),
                headers={
                    "User-Agent": f"{APP_NAME}/{__version__}",
                    "Accept": "application/octet-stream",
                },
            )
            digest = hashlib.sha256()
            downloaded = 0
            with urllib.request.urlopen(
                request, timeout=30.0, context=_ssl_context()
            ) as response:
                if not _host_allowed(response.geturl()):
                    self._fail("invalid_asset", part)
                    return
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > _MAX_UPDATE_BYTES:
                    self._fail("invalid_asset", part)
                    return
                with part.open("wb") as handle:
                    while True:
                        if self._cancel.is_set():
                            self._fail("cancelled", part)
                            return
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > _MAX_UPDATE_BYTES:
                            self._fail("invalid_asset", part)
                            return
                        handle.write(chunk)
                        digest.update(chunk)
                        self._update(
                            state="downloading",
                            bytes=downloaded,
                            totalBytes=total,
                            percent=round(min(downloaded / total, 1.0) * 100, 1),
                        )
            if downloaded != total:
                self._fail("size_mismatch", part)
                return
            self._update(state="verifying", percent=100.0)
            actual = digest.hexdigest()
            if actual != expected:
                self._fail("checksum_mismatch", part)
                return
            os.replace(part, destination)
            self._update(
                state="ready",
                path=str(destination),
                bytes=downloaded,
                totalBytes=total,
                percent=100.0,
                sha256=actual,
                error=None,
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            log.info("update download failed", exc_info=True)
            self._fail("download_failed", part)


update_manager = UpdateDownloadManager()
