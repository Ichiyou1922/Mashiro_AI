#!/bin/bash

VOICEVOX_CONTAINER="mashiro_voicevox"
TMUX_SESSION="mashiro"

# --- ましろ本体 停止 ---
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    tmux kill-session -t "$TMUX_SESSION"
    echo "Mashiro stopped"
else
    echo "Mashiro is not running"
fi

# --- VOICEVOX 停止 ---
if docker ps --format '{{.Names}}' | grep -q "^${VOICEVOX_CONTAINER}$"; then
    docker stop "$VOICEVOX_CONTAINER"
    echo "VOICEVOX stopped"
else
    echo "VOICEVOX is not running"
fi
