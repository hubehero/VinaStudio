"""Run the desktop application against the Vite dev server with hot reload.

The Qt process starts the API on a fixed loopback port; Vite proxies ``/api``
and ``/ws`` to it (see ``web/vite.config.ts``), so there is no third process to
manage.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

DEFAULT_VITE_PORT = 5173
DEFAULT_API_PORT = 8756
STARTUP_TIMEOUT = 60.0

log = logging.getLogger("dev")


def find_pnpm() -> str:
    for candidate in ("pnpm", "pnpm.cmd"):
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("pnpm was not found on PATH; see https://pnpm.io/installation")


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout: float, *, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_is_open(host, port):
            log.info("%s is accepting connections on %s:%d", label, host, port)
            return
        time.sleep(0.25)
    raise SystemExit(f"{label} did not start on {host}:{port} within {timeout:.0f}s")


def pump_output(process: subprocess.Popen[str], prefix: str) -> threading.Thread:
    """Forward a child's combined output to our stderr, line by line."""

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stderr.write(f"[{prefix}] {line}")

    thread = threading.Thread(target=reader, name=f"pump-{prefix}", daemon=True)
    thread.start()
    return thread


def terminate(process: subprocess.Popen[str] | None, name: str) -> None:
    """Stop a child process group, escalating only if it ignores SIGTERM."""
    if process is None or process.poll() is not None:
        return
    log.info("Stopping %s (pid %d)", name, process.pid)
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log.warning("%s ignored SIGTERM; killing it", name)
        process.kill()
        process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vite-port", type=int, default=DEFAULT_VITE_PORT)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging in the desktop app."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not (WEB_DIR / "node_modules").is_dir():
        raise SystemExit(
            "Interface dependencies are missing. Run:\n"
            f"  pnpm -C {WEB_DIR.relative_to(REPO_ROOT)} install"
        )

    pnpm = find_pnpm()
    vite: subprocess.Popen[str] | None = None
    desktop: subprocess.Popen[str] | None = None

    def handle_signal(signum: int, _frame: object) -> None:
        log.info("Received signal %d; shutting down", signum)
        terminate(desktop, "desktop app")
        terminate(vite, "vite")
        sys.exit(130)

    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), handle_signal)

    try:
        vite_env = {**os.environ, "VINASTUDIO_DEV_API_PORT": str(args.api_port)}
        vite = subprocess.Popen(
            [pnpm, "run", "dev", "--port", str(args.vite_port)],
            cwd=WEB_DIR,
            env=vite_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        pump_output(vite, "vite")

        if vite.poll() is not None:
            return vite.returncode or 1
        wait_for_port("127.0.0.1", args.vite_port, STARTUP_TIMEOUT, label="Vite")

        desktop_env = {
            **os.environ,
            "VINASTUDIO_DEV_SERVER_URL": f"http://127.0.0.1:{args.vite_port}",
            "VINASTUDIO_DEV_API_PORT": str(args.api_port),
        }
        desktop_command = [
            sys.executable,
            "-m",
            "vinastudio",
            "--api-port",
            str(args.api_port),
        ]
        if args.verbose:
            desktop_command.append("--verbose")

        log.info("Launching desktop shell: %s", " ".join(desktop_command))
        desktop = subprocess.Popen(desktop_command, cwd=REPO_ROOT, env=desktop_env)

        while desktop.poll() is None and vite.poll() is None:
            time.sleep(0.5)

        if vite.poll() is not None:
            log.error("Vite exited with code %s", vite.returncode)
        return desktop.poll() if desktop.poll() is not None else 1
    finally:
        terminate(desktop, "desktop app")
        terminate(vite, "vite")


if __name__ == "__main__":
    sys.exit(main())
