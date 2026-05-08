#!/bin/bash
###############################################################################
# Ollama-Qwen Service Manager
# Start, stop, restart, switch models, and check proxy status
###############################################################################

INSTALL_DIR="$HOME/.ollama-qwen"
PROXY_SCRIPT="$INSTALL_DIR/ollama-proxy.py"
CONFIG_FILE="$INSTALL_DIR/config.json"
PROXY_LOG="$INSTALL_DIR/proxy.log"
DEFAULT_PORT=8001
DEFAULT_MODEL=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $1"; }
error()   { echo -e "${RED}[ERR]${NC}    $1"; }

###############################################################################
# Config management
###############################################################################
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        PROXY_PORT=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('port', $DEFAULT_PORT))" 2>/dev/null || echo $DEFAULT_PORT)
        CURRENT_MODEL=$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('model', '$DEFAULT_MODEL'))" 2>/dev/null || echo "$DEFAULT_MODEL")
    else
        PROXY_PORT=$DEFAULT_PORT
        CURRENT_MODEL=""
    fi
}

save_config() {
    local port="$1"
    local model="$2"
    python3 -c "
import json
config = {'port': $port, 'model': '$model'}
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
"
}

###############################################################################
# Get proxy PID
###############################################################################
get_proxy_pid() {
    pgrep -f "ollama-proxy.py" 2>/dev/null | head -1
}

###############################################################################
# Check status
###############################################################################
cmd_status() {
    load_config

    echo -e "${CYAN}━━━ Ollama-Qwen Proxy Status ━━━${NC}\n"

    local pid
    pid=$(get_proxy_pid)

    if [ -n "$pid" ]; then
        echo -e "  Proxy:  ${GREEN}RUNNING${NC} (PID: $pid)"
    else
        echo -e "  Proxy:  ${RED}STOPPED${NC}"
    fi

    # Check health endpoint
    if curl -sf "http://localhost:${PROXY_PORT:-$DEFAULT_PORT}/health" &>/dev/null; then
        local health
        health=$(curl -sf "http://localhost:${PROXY_PORT:-$DEFAULT_PORT}/health" 2>/dev/null)
        echo -e "  Health: ${GREEN}OK${NC}"
        echo "  $health" | python3 -c "
import sys, json
try:
    h = json.load(sys.stdin)
    print(f\"  Model:  {h.get('default_model', 'N/A')}\")
    print(f\"  Ollama: {'Connected' if h.get('ollama_connected') else 'Disconnected'}\")
except: pass
" 2>/dev/null
    else
        echo -e "  Health: ${RED}Not responding${NC}"
    fi

    # Ollama status
    if curl -sf http://localhost:11434/api/tags &>/dev/null; then
        echo -e "  Ollama: ${GREEN}Connected${NC} (localhost:11434)"
    else
        echo -e "  Ollama: ${RED}Not connected${NC}"
    fi

    # Current config
    if [ -f "$CONFIG_FILE" ]; then
        echo -e "\n  ${CYAN}Config:${NC}"
        echo "    Port: ${PROXY_PORT:-$DEFAULT_PORT}"
        echo "    Model: ${CURRENT_MODEL:-not set}"
    fi

    echo ""
}

###############################################################################
# Start proxy
###############################################################################
cmd_start() {
    load_config

    local pid
    pid=$(get_proxy_pid)
    if [ -n "$pid" ]; then
        warn "Proxy is already running (PID: $pid)"
        return 0
    fi

    # Check Ollama
    if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
        error "Ollama is not running. Start it first."
        return 1
    fi

    # Check proxy script
    if [ ! -f "$PROXY_SCRIPT" ]; then
        error "Proxy script not found at $PROXY_SCRIPT"
        echo "    Run the installer first."
        return 1
    fi

    # Build command
    local cmd="nohup python3 $PROXY_SCRIPT --port ${PROXY_PORT:-$DEFAULT_PORT}"
    if [ -n "$CURRENT_MODEL" ]; then
        cmd="$cmd --model $CURRENT_MODEL"
    fi
    cmd="$cmd > $PROXY_LOG 2>&1 &"

    info "Starting proxy..."
    eval $cmd

    sleep 3

    if get_proxy_pid &>/dev/null; then
        success "Proxy started on port ${PROXY_PORT:-$DEFAULT_PORT}"
        if [ -n "$CURRENT_MODEL" ]; then
            success "Model: $CURRENT_MODEL"
        fi
        info "Log: tail -f $PROXY_LOG"
    else
        error "Proxy failed to start"
        error "Log output:"
        cat "$PROXY_LOG" 2>/dev/null | tail -20
        return 1
    fi
}

###############################################################################
# Stop proxy
###############################################################################
cmd_stop() {
    local pid
    pid=$(get_proxy_pid)

    if [ -z "$pid" ]; then
        warn "Proxy is not running"
        return 0
    fi

    info "Stopping proxy (PID: $pid)..."
    kill "$pid" 2>/dev/null

    # Wait for process to exit
    local retries=5
    while kill -0 "$pid" 2>/dev/null && [ $retries -gt 0 ]; do
        sleep 1
        retries=$((retries - 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "Force killing..."
        kill -9 "$pid" 2>/dev/null
    fi

    success "Proxy stopped"
}

###############################################################################
# Restart proxy
###############################################################################
cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

###############################################################################
# List models
###############################################################################
cmd_models() {
    echo -e "${CYAN}━━━ Available Ollama Models ━━━${NC}\n"

    local models
    models=$(curl -sf http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('models', [])
if not models:
    print('No models found.')
    print('Pull one: ollama pull qwen2.5-coder:14b')
    sys.exit()
for m in models:
    name = m['name']
    size = m.get('details', {}).get('parameter_size', '?')
    family = m.get('details', {}).get('family', '?')
    quant = m.get('details', {}).get('quantization_level', '?')
    print(f'{name}  |  {size}  |  {family}  |  {quant}')
" 2>/dev/null)

    if [ -n "$models" ]; then
        echo -e "  ${BLUE}Name${NC}  |  ${BLUE}Size${NC}  |  ${BLUE}Family${NC}  |  ${BLUE}Quant${NC}"
        echo "  ──────────────────────────────────────────────────────"
        echo "$models" | while IFS= read -r line; do
            echo "  $line"
        done
    fi
    echo ""
}

###############################################################################
# Switch model
###############################################################################
cmd_switch() {
    local new_model="$1"

    # If no model specified, show interactive selector
    if [ -z "$new_model" ]; then
        echo -e "${CYAN}━━━ Switch Model ━━━${NC}\n"

        local models
        models=$(curl -sf http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(m['name'])
" 2>/dev/null)

        if [ -z "$models" ]; then
            error "No models available"
            return 1
        fi

        IFS=$'\n' read -d '' -ra MODEL_ARRAY <<< "$models"

        echo -e "  ${BLUE}Available models:${NC}"
        for i in "${!MODEL_ARRAY[@]}"; do
            local marker=""
            load_config
            if [ "${MODEL_ARRAY[$i]}" = "$CURRENT_MODEL" ]; then
                marker=" (current)"
            fi
            echo -e "    ${GREEN}$((i+1))${NC}) ${MODEL_ARRAY[$i]}$marker"
        done
        echo ""

        while true; do
            read -p "  Select model (1-${#MODEL_ARRAY[@]}): " choice
            if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#MODEL_ARRAY[@]}" ]; then
                new_model="${MODEL_ARRAY[$((choice-1))]}"
                break
            else
                error "Invalid selection"
            fi
        done
    fi

    # Save new config
    load_config
    save_config "${PROXY_PORT:-$DEFAULT_PORT}" "$new_model"
    success "Switched to: $new_model"

    # Restart proxy with new model
    info "Restarting proxy..."
    cmd_restart

    echo ""
    success "Model switched to: $new_model"
    info "Test: curl -s http://localhost:${PROXY_PORT:-$DEFAULT_PORT}/health"
}

###############################################################################
# Show logs
###############################################################################
cmd_logs() {
    if [ -f "$PROXY_LOG" ]; then
        tail -f "$PROXY_LOG"
    else
        warn "No log file found at $PROXY_LOG"
    fi
}

###############################################################################
# Help
###############################################################################
cmd_help() {
    echo -e "${CYAN}━━━ Ollama-Qwen Service Manager ━━━${NC}
${BLUE}Usage:${NC} $(basename "$0") <command>

${BLUE}Commands:${NC}
  start          Start the proxy
  stop           Stop the proxy
  restart        Restart the proxy
  status         Show proxy status and health
  models         List available Ollama models
  switch [name]  Switch to a different model (interactive if no name given)
  logs           Follow proxy logs

${BLUE}Quick Start Aliases:${NC} (add to ~/.bashrc)
  ollama-qwen-start    → service.sh start
  ollama-qwen-stop     → service.sh stop
  ollama-qwen-restart  → service.sh restart
  ollama-qwen-status   → service.sh status
  ollama-qwen-models   → service.sh models
  ollama-qwen-switch   → service.sh switch
  ollama-qwen-logs     → tail -f proxy.log
"
}

###############################################################################
# Main
###############################################################################
case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    models)  cmd_models ;;
    switch)  cmd_switch "$2" ;;
    logs)    cmd_logs ;;
    help|--help|-h) cmd_help ;;
    *)
        error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
