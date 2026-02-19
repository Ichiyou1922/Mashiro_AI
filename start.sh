#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VOICEVOX_CONTAINER="mashiro_voicevox"
TMUX_SESSION="mashiro"

# 引数チェック
#if [ "$1" != "gpu" ] && [ "$1" != "cpu" ]; then
#    echo "Usage: ./start.sh [gpu|cpu]"
#    exit 1
#fi

# --- 二重起動チェック ---
if docker ps --format '{{.Names}}' | grep -q "^${VOICEVOX_CONTAINER}$"; then
    echo "VOICEVOX is already running"
    exit 1
fi

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Mashiro is already running"
    exit 1
fi

# --- VOICEVOX 起動 ---
if [ "$1" = "gpu" ] || [ "$1" = "cpu" ]; then
    echo "Starting VOICEVOX ($1 mode)..."
    if [ "$1" = "gpu" ]; then
        docker run --rm -d --gpus all -p 50021:50021 --name "$VOICEVOX_CONTAINER" \
            voicevox/voicevox_engine:nvidia-ubuntu20.04-latest
    else
        docker run --rm -d -p 50021:50021 --name "$VOICEVOX_CONTAINER" \
            voicevox/voicevox_engine:cpu-ubuntu20.04-latest
    fi
else
    echo "azure tts mode selected, skipping VOICEVOX container startup"

fi

# --- ましろ本体 起動 ---
echo "Starting Mashiro..."
tmux new-session -d -s "$TMUX_SESSION" "cd '$SCRIPT_DIR' && source brain/.venv/bin/activate && python brain/src/main.py 2>&1"


echo ""
echo "=== Started ==="
echo "VOICEVOX: $1 mode (container: $VOICEVOX_CONTAINER)"
echo "Mashiro:  tmux session '$TMUX_SESSION'"
echo ""
echo "Log: tmux attach -t $TMUX_SESSION  (detach: Ctrl+B, D)"
