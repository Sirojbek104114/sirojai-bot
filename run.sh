#!/bin/bash

# SirojAIorg_bot - auto-restart launcher
while true; do
    echo "$(date) - Bot ishga tushmoqda..."
    python3 /workspace/bot.py
    echo "$(date) - Bot to'xtadi (xatolik?). 5 soniyadan keyin qayta ishga tushadi."
    sleep 5
done
