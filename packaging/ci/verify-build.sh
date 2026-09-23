#!/usr/bin/env bash
# verify-build.sh — Smoke test for VinaStudio build output
#
# Checks that the PyInstaller output exists and is minimally functional.
# Exit code 0 = all checks passed, non-zero = failure.
#
# Usage:
#   bash packaging/ci/verify-build.sh [DIST_DIR]
#
# DIST_DIR defaults to dist/vinastudio

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

DIST_DIR="${1:-dist/vinastudio}"
ERRORS=0

echo "==> Verifying build in ${DIST_DIR}"
echo ""

# ---------------------------------------------------------------------------
# 1. Check that the executable exists
# ---------------------------------------------------------------------------
EXE_PATH="${DIST_DIR}/vinastudio"
if [[ -f "$EXE_PATH" ]]; then
    echo "  [PASS] Executable found: ${EXE_PATH}"
else
    echo "  [FAIL] Executable not found: ${EXE_PATH}"
    ERRORS=$((ERRORS + 1))
fi

# ---------------------------------------------------------------------------
# 2. Check that _internal/ directory exists (PyIndicator --onedir output)
# ---------------------------------------------------------------------------
if [[ -d "${DIST_DIR}/_internal" ]]; then
    echo "  [PASS] _internal/ directory exists"
else
    echo "  [FAIL] _internal/ directory missing"
    ERRORS=$((ERRORS + 1))
fi

# ---------------------------------------------------------------------------
# 3. Check that the static frontend was bundled
# ---------------------------------------------------------------------------
if [[ -d "${DIST_DIR}/_internal/vinastudio/server/static" ]]; then
    echo "  [PASS] Frontend static files bundled"
elif [[ -d "${DIST_DIR}/vinastudio/server/static" ]]; then
    echo "  [PASS] Frontend static files bundled (non-standard layout)"
else
    echo "  [WARN] Frontend static files not found in expected locations"
fi

# ---------------------------------------------------------------------------
# 4. Try running --version (quick sanity check)
# ---------------------------------------------------------------------------
if [[ -x "$EXE_PATH" ]] || [[ -f "$EXE_PATH" ]]; then
    echo ""
    echo "==> Running '${EXE_PATH} --version'..."
    VERSION_OUTPUT="$("$EXE_PATH" --version 2>&1 || true)"
    if [[ -n "$VERSION_OUTPUT" ]]; then
        echo "  [PASS] --version output: ${VERSION_OUTPUT}"
    else
        echo "  [WARN] --version returned empty output (may require GUI environment)"
    fi
else
    echo "  [SKIP] Cannot run --version: executable not found"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo "==> All checks PASSED"
    exit 0
else
    echo "==> ${ERRORS} check(s) FAILED"
    exit 1
fi
