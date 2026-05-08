#!/bin/bash
# Start/restart Ollama-Qwen proxy with health check
pkill -9 -f "qwen_api.py" 2>/dev/null
sleep 2
nohup python3 /home/dev/qwen_api.py > /dev/null 2>&1 &
sleep 3

if curl -sf http://127.0.0.1:8001/v1/models > /dev/null 2>&1; then
    echo "✅ Proxy started (PID: $(pgrep -f qwen_api))"
else
    echo "❌ Proxy failed to start"
    exit 1
fi
