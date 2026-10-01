#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

HOST="${ALEXANDRIA_HOST:-0.0.0.0}"
PORT="${ALEXANDRIA_PORT:-4200}"
DATA_DIR="${ALEXANDRIA_DATA_DIR:-/workspace/alexandria}"
CONFIG_PATH="${ALEXANDRIA_CONFIG_PATH:-${DATA_DIR}/config/config.json}"
MODELS_DIR="${ALEXANDRIA_MODELS_DIR:-${DATA_DIR}/models}"
OUTPUT_DIR="${ALEXANDRIA_OUTPUT_DIR:-${DATA_DIR}/final}"
HF_CACHE="${HF_HOME:-${DATA_DIR}/cache/huggingface}"
BUILTIN_LORA="${ALEXANDRIA_ENABLE_BUILTIN_LORA:-false}"
TIMEZONE="${TZ:-Asia/Shanghai}"
PID_FILE="${DATA_DIR}/app.pid"
LOG_FILE="${DATA_DIR}/app.log"

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "错误：无效端口 ALEXANDRIA_PORT=${PORT}" >&2
    exit 1
fi

PYTHON_BIN="${ALEXANDRIA_PYTHON:-/workspace/venvs/novel-voice/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
        PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        echo "错误：找不到 Python。可通过 ALEXANDRIA_PYTHON 指定解释器路径。" >&2
        exit 1
    fi
fi

mkdir -p \
    "$DATA_DIR" \
    "$(dirname -- "$CONFIG_PATH")" \
    "$MODELS_DIR" \
    "$OUTPUT_DIR" \
    "$HF_CACHE"

listener_pids() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "sport = :${PORT}" 2>/dev/null \
            | grep -oE 'pid=[0-9]+' \
            | cut -d= -f2 \
            | sort -u || true
    elif command -v lsof >/dev/null 2>&1; then
        lsof -nP -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
    elif command -v fuser >/dev/null 2>&1; then
        fuser "${PORT}/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true
    fi
}

is_running() {
    local pid="$1"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

is_project_process() {
    local pid="$1"
    [[ -r "/proc/${pid}/cmdline" ]] || return 1
    tr '\0' ' ' < "/proc/${pid}/cmdline" | grep -Fq 'app/app.py'
}

PIDS=""
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(tr -dc '0-9' < "$PID_FILE")"
    if [[ -n "$OLD_PID" ]] && is_running "$OLD_PID" && is_project_process "$OLD_PID"; then
        PIDS="${PIDS} ${OLD_PID}"
    fi
fi

while IFS= read -r pid; do
    [[ -n "$pid" ]] && PIDS="${PIDS} ${pid}"
done < <(listener_pids)

if [[ -n "${PIDS// /}" ]]; then
    echo "检测到旧服务或端口 ${PORT} 被占用，正在停止：${PIDS}"
    for pid in $PIDS; do
        is_running "$pid" && kill "$pid" 2>/dev/null || true
    done

    for _ in {1..20}; do
        survivors=""
        for pid in $PIDS; do
            is_running "$pid" && survivors="${survivors} ${pid}"
        done
        [[ -z "${survivors// /}" ]] && break
        sleep 0.5
    done

    for pid in $PIDS; do
        if is_running "$pid"; then
            echo "进程 ${pid} 未正常退出，执行强制停止。"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
fi

rm -f "$PID_FILE"

REMAINING="$(listener_pids | tr '\n' ' ')"
if [[ -n "${REMAINING// /}" ]]; then
    echo "错误：端口 ${PORT} 仍被进程占用：${REMAINING}" >&2
    exit 1
fi

cd "$ROOT_DIR"
echo "正在启动 Novel Voice Studio..."

nohup env \
    ALEXANDRIA_HOST="$HOST" \
    ALEXANDRIA_PORT="$PORT" \
    ALEXANDRIA_DATA_DIR="$DATA_DIR" \
    ALEXANDRIA_CONFIG_PATH="$CONFIG_PATH" \
    ALEXANDRIA_MODELS_DIR="$MODELS_DIR" \
    ALEXANDRIA_OUTPUT_DIR="$OUTPUT_DIR" \
    ALEXANDRIA_ENABLE_BUILTIN_LORA="$BUILTIN_LORA" \
    HF_HOME="$HF_CACHE" \
    TZ="$TIMEZONE" \
    "$PYTHON_BIN" app/app.py \
    > "$LOG_FILE" 2>&1 < /dev/null &

NEW_PID=$!

for _ in {1..30}; do
    if ! is_running "$NEW_PID"; then
        echo "错误：服务启动失败。最近日志：" >&2
        tail -n 80 "$LOG_FILE" >&2 || true
        exit 1
    fi

    if command -v curl >/dev/null 2>&1; then
        if curl -fsS "http://127.0.0.1:${PORT}/openapi.json" >/dev/null 2>&1; then
            printf '%s\n' "$NEW_PID" > "$PID_FILE"
            echo "启动成功：PID=${NEW_PID}，端口=${PORT}"
            echo "日志文件：${LOG_FILE}"
            exit 0
        fi
    elif listener_pids | grep -qx "$NEW_PID"; then
        printf '%s\n' "$NEW_PID" > "$PID_FILE"
        echo "启动成功：PID=${NEW_PID}，端口=${PORT}"
        echo "日志文件：${LOG_FILE}"
        exit 0
    fi

    sleep 1
done

echo "错误：服务在 30 秒内未通过健康检查。最近日志：" >&2
tail -n 80 "$LOG_FILE" >&2 || true
kill "$NEW_PID" 2>/dev/null || true
exit 1
