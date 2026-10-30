#!/usr/bin/env bash
# Start the VinaStudio web interface without the Qt desktop shell.
#
# FastAPI serves the local API and Vite serves the SPA with hot reload. Vite
# proxies /api, /artifacts and /ws to the API, so the browser only needs the
# Vite origin. Keeping both children in the foreground (with a terminal window
# when launched from a file manager) makes Ctrl+C the single stop action.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${WEB_API_PORT:-8756}"
VITE_PORT="${WEB_VITE_PORT:-5173}"
WEB_URL="http://127.0.0.1:${VITE_PORT}"

# A desktop double-click has no terminal to print logs into or receive Ctrl+C.
# Re-exec inside one unless the caller explicitly disabled this behavior.
if [ "${WEB_START_NO_TERMINAL:-0}" != "1" ] \
    && [ ! -t 0 ] && [ ! -t 1 ] \
    && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] \
    && command -v x-terminal-emulator >/dev/null 2>&1; then
    exec x-terminal-emulator -e env WEB_START_AUTO_TERMINAL=1 "$ROOT/web_start.sh" "$@"
fi

cd "$ROOT"

# The terminal is the only place errors are visible when this was launched by
# a double-click. Hold it open instead of letting the window vanish instantly.
fail() {
    echo "$*" >&2
    if [ "${WEB_START_AUTO_TERMINAL:-0}" = "1" ] && [ -t 0 ]; then
        echo >&2
        read -r -p "按 Enter 关闭窗口…" _ || true
    fi
    exit 1
}

for command_name in uv pnpm; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        case "$command_name" in
            uv) fail "缺少命令：uv（https://docs.astral.sh/uv/）" ;;
            pnpm) fail "缺少命令：pnpm（https://pnpm.io/installation）" ;;
        esac
    fi
done

if [ ! -d "$ROOT/web/node_modules" ]; then
    echo "首次运行：安装前端依赖…"
    pnpm -C "$ROOT/web" install --frozen-lockfile || fail "前端依赖安装失败。"
fi

port_is_open() {
    (echo >"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

port_owner_pid() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "sport = :$1" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
            | head -n 1
    elif command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1
    fi
}

# True when this process still has a live web_start.sh ancestor. The normal
# launcher keeps both children under that shell, so a second launch must not
# steal its ports. Orphans from a closed/crashed terminal have no such ancestor.
managed_by_launcher() {
    local pid="$1"
    local depth=0
    while [ "$pid" -gt 1 ] && [ "$depth" -lt 8 ]; do
        if ps -o cmd= -p "$pid" 2>/dev/null | grep -q 'web_start\.sh'; then
            return 0
        fi
        pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
        [ -n "$pid" ] || return 1
        depth=$((depth + 1))
    done
    return 1
}

# A terminal closed with HUP normally runs the EXIT trap, but a killed terminal
# can leave uvicorn/Vite orphaned. Reclaim only processes that are demonstrably
# this checkout's services; an unrelated program on the port is still an error.
reclaim_stale_service() {
    local port="$1"
    local pid cmd cwd pgid
    port_is_open "$port" || return 0

    pid=$(port_owner_pid "$port" || true)
    [ -n "$pid" ] || return 1
    cmd=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)

    if [ "$port" = "$API_PORT" ] \
        && [[ "$cmd" == *"vinastudio.server.app:create_app"* ]] \
        && [ "$cwd" = "$ROOT" ]; then
        :
    elif [ "$port" = "$VITE_PORT" ] \
        && [[ "$cmd" == *"vite"* ]] \
        && [ "$cwd" = "$ROOT/web" ]; then
        :
    else
        return 1
    fi

    if managed_by_launcher "$pid"; then
        fail "已有 VinaStudio Web 实例在运行（端口 $port）。请在原终端按 Ctrl+C，或先关闭那个窗口。"
    fi

    echo "发现上次残留的 VinaStudio 服务（端口 $port），先清理…"
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
    if [ -n "$pgid" ]; then
        kill -TERM -- "-$pgid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    else
        kill -TERM "$pid" 2>/dev/null || true
    fi
    for _ in $(seq 1 40); do
        port_is_open "$port" || return 0
        sleep 0.25
    done
    [ -n "$pgid" ] && kill -KILL -- "-$pgid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
    sleep 0.25
    port_is_open "$port" && return 1
    return 0
}

for port in "$API_PORT" "$VITE_PORT"; do
    if port_is_open "$port"; then
        reclaim_stale_service "$port" || fail \
            "端口 $port 已被其他程序占用。请先关闭占用进程，或用 WEB_API_PORT / WEB_VITE_PORT 指定其他端口。"
    fi
done

api_pid=""
vite_pid=""

cleanup() {
    trap - EXIT
    echo
    echo "正在关闭 VinaStudio Web…"
    for pid in "$vite_pid" "$api_pid"; do
        [ -n "$pid" ] || continue
        # setsid makes each service its own process-group leader, so this also
        # stops the node/uvicorn children that pnpm/uv would otherwise leave.
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done
    wait "$vite_pid" "$api_pid" 2>/dev/null || true
    echo "已关闭。"
}

trap cleanup EXIT
# Closing the terminal sends HUP; the services live in their own sessions, so
# the EXIT trap is what actually stops them.
trap 'exit 130' INT TERM HUP

# VINASTUDIO_DEV_SERVER_URL enables the dev CORS policy. The Vite proxy means
# the browser never calls the API cross-origin, but keeping the flag matches the
# desktop dev launcher and avoids surprising direct API requests.
setsid env VINASTUDIO_DEV_SERVER_URL="$WEB_URL" \
    uv run uvicorn vinastudio.server.app:create_app \
    --factory --host 127.0.0.1 --port "$API_PORT" --log-level info &
api_pid=$!

setsid env VINASTUDIO_DEV_API_PORT="$API_PORT" \
    pnpm --dir "$ROOT/web" exec vite \
    --host 127.0.0.1 --port "$VITE_PORT" &
vite_pid=$!

for _ in $(seq 1 240); do
    if port_is_open "$API_PORT" && port_is_open "$VITE_PORT"; then
        break
    fi
    if ! kill -0 "$api_pid" 2>/dev/null || ! kill -0 "$vite_pid" 2>/dev/null; then
        fail "启动失败：某个服务提前退出，请查看上方日志。"
    fi
    sleep 0.25
done

if ! port_is_open "$API_PORT" || ! port_is_open "$VITE_PORT"; then
    fail "启动超时：API $API_PORT 或 Vite $VITE_PORT 未就绪。"
fi

echo
echo "VinaStudio Web 已启动：$WEB_URL"
echo "API: http://127.0.0.1:$API_PORT"
echo "按 Ctrl+C 关闭（终端保持前台，关闭窗口不会留下后台服务）。"
echo

if [ "${WEB_START_NO_BROWSER:-0}" != "1" ] && command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$WEB_URL" >/dev/null 2>&1 &
fi

# Keep the launcher alive for as long as both services are healthy. If one
# dies, cleanup stops the other instead of leaving a half-running test setup.
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$vite_pid" 2>/dev/null; do
    sleep 1
done

status=1
kill -0 "$api_pid" 2>/dev/null || echo "API 已退出。" >&2
kill -0 "$vite_pid" 2>/dev/null || echo "Vite 已退出。" >&2
exit "$status"
