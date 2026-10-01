#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${ALEXANDRIA_DATA_DIR:-/workspace/alexandria}"
VENV_DIR="${ALEXANDRIA_VENV_DIR:-/workspace/venvs/novel-voice}"
BASE_PYTHON="${ALEXANDRIA_BASE_PYTHON:-python3}"
MARKER_FILE="${VENV_DIR}/.novel-voice-bootstrap"
REQUIREMENTS_FILE="${ROOT_DIR}/app/requirements.txt"
QWEN_TTS_VERSION="0.1.1"

CHECK_ONLY=false
START_AFTER=true
FORCE_REBUILD=false

usage() {
    cat <<'EOF'
用法：./bootstrap.sh [选项]

  --check       只检查环境，不安装也不启动
  --no-start    检查并安装环境，但不启动 Web 服务
  --force       强制重建 Python 虚拟环境
  -h, --help    显示帮助
EOF
}

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true; START_AFTER=false ;;
        --no-start) START_AFTER=false ;;
        --force) FORCE_REBUILD=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "错误：未知参数 ${arg}" >&2; usage >&2; exit 2 ;;
    esac
done

echo "=== Novel Voice Studio 环境检测 ==="
echo "项目目录：${ROOT_DIR}"
echo "数据目录：${DATA_DIR}"
echo "虚拟环境：${VENV_DIR}"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    echo "错误：找不到 ${REQUIREMENTS_FILE}" >&2
    exit 1
fi

if ! command -v "$BASE_PYTHON" >/dev/null 2>&1; then
    echo "错误：找不到基础 Python：${BASE_PYTHON}" >&2
    exit 1
fi
BASE_PYTHON="$(command -v "$BASE_PYTHON")"

missing_commands=()
command -v ffmpeg >/dev/null 2>&1 || missing_commands+=(ffmpeg)
command -v sox >/dev/null 2>&1 || missing_commands+=(sox)
command -v git >/dev/null 2>&1 || missing_commands+=(git)
command -v curl >/dev/null 2>&1 || missing_commands+=(curl)
command -v ss >/dev/null 2>&1 || missing_commands+=(ss)
VENV_MODULE_AVAILABLE=true
"$BASE_PYTHON" -c 'import venv' >/dev/null 2>&1 || VENV_MODULE_AVAILABLE=false

if (( ${#missing_commands[@]} > 0 )) || ! $VENV_MODULE_AVAILABLE; then
    echo "缺少系统命令：${missing_commands[*]}"
    $VENV_MODULE_AVAILABLE || echo "缺少 Python venv 模块"
    if $CHECK_ONLY; then
        echo "检测未通过：需要安装系统依赖。" >&2
        exit 1
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "错误：当前镜像没有 apt-get，请改用 RunPod 的 PyTorch/Ubuntu 镜像。" >&2
        exit 1
    fi
    echo "正在安装系统依赖..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        sox \
        libsox-dev \
        libsox-fmt-all \
        git \
        curl \
        iproute2 \
        python3-venv \
        ca-certificates
    rm -rf /var/lib/apt/lists/*
else
    echo "系统依赖：正常"
fi

if ! $CHECK_ONLY; then
    mkdir -p \
        "$DATA_DIR" \
        "${DATA_DIR}/config" \
        "${DATA_DIR}/models" \
        "${DATA_DIR}/final" \
        "${DATA_DIR}/cache/huggingface" \
        "$(dirname -- "$VENV_DIR")"
fi

BASE_FINGERPRINT="$($BASE_PYTHON - <<'PY'
import platform
import sys
print(f"python={sys.version_info.major}.{sys.version_info.minor};arch={platform.machine()}")
PY
)"
REQ_HASH="$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}')"
EXPECTED_MARKER="${BASE_FINGERPRINT};requirements=${REQ_HASH};qwen-tts=${QWEN_TTS_VERSION}"

REBUILD=false
INSTALL=false

if $FORCE_REBUILD; then
    REBUILD=true
    INSTALL=true
elif [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    REBUILD=true
    INSTALL=true
elif ! "${VENV_DIR}/bin/python" -c 'import sys; print(sys.version)' >/dev/null 2>&1; then
    REBUILD=true
    INSTALL=true
elif [[ ! -f "$MARKER_FILE" ]] || [[ "$(cat "$MARKER_FILE")" != "$EXPECTED_MARKER" ]]; then
    INSTALL=true
elif ! "${VENV_DIR}/bin/python" - <<'PY' >/dev/null 2>&1
import aiofiles
import fastapi
import gradio_client
import numpy
import openai
import pydub
import qwen_tts
import soundfile
import torch
import transformers
import uvicorn
PY
then
    INSTALL=true
fi

if $CHECK_ONLY; then
    if $REBUILD || $INSTALL; then
        echo "Python 环境：需要安装或更新"
        exit 1
    fi
    echo "Python 环境：正常"
else
    if $REBUILD; then
        echo "正在创建 Python 虚拟环境..."
        "$BASE_PYTHON" -m venv --clear --system-site-packages "$VENV_DIR"
    fi

    if $INSTALL; then
        echo "正在安装或更新 Python 依赖..."
        "${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
        "${VENV_DIR}/bin/python" -m pip install -r "$REQUIREMENTS_FILE"
        "${VENV_DIR}/bin/python" -m pip install \
            "qwen-tts==${QWEN_TTS_VERSION}" \
            "hf_transfer>=0.1.8,<1"
        printf '%s\n' "$EXPECTED_MARKER" > "$MARKER_FILE"
    else
        echo "Python 环境：已存在且版本匹配，跳过安装"
    fi
fi

echo "正在验证运行环境..."
"${VENV_DIR}/bin/python" - <<'PY'
import shutil
import sys

import fastapi
import qwen_tts
import soundfile
import torch
import uvicorn

print(f"Python: {sys.version.split()[0]}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA 可用: {'是' if torch.cuda.is_available() else '否'}")
print(f"ffmpeg: {shutil.which('ffmpeg')}")
print(f"sox: {shutil.which('sox')}")
PY

MODEL_FILES="$(find "${DATA_DIR}/models" -type f \( -name 'config.json' -o -name '*.safetensors' \) 2>/dev/null | wc -l | tr -d ' ')"
echo "持久化模型文件检查：发现 ${MODEL_FILES:-0} 个配置或权重文件（不会自动下载模型）"

if $START_AFTER; then
    echo "环境准备完成，正在启动服务..."
    ALEXANDRIA_PYTHON="${VENV_DIR}/bin/python" "${ROOT_DIR}/start.sh"
else
    echo "环境准备完成。"
fi
