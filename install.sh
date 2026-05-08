#!/bin/bash
###############################################################################
# Ollama-Qwen CLI Installer
# One-click setup for using any Ollama model with Qwen Code CLI via tool calling
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.ollama-qwen"
PROXY_PORT=8001
PROXY_LOG="$INSTALL_DIR/proxy.log"

# Banners
banner() {
    echo -e "\n${CYAN}╔══════════════════════════════════════════════════════════╗"
    echo -e "║  ${YELLOW}Ollama → Qwen Code CLI${CYAN} Tool Calling Bridge                ║"
    echo -e "╚══════════════════════════════════════════════════════════╝${NC}\n"
}

info()    { echo -e "  ${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "  ${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "  ${YELLOW}[WARN]${NC}   $1"; }
error()   { echo -e "  ${RED}[ERR]${NC}    $1"; }
step()    { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

###############################################################################
# Pre-flight checks
###############################################################################
check_prerequisites() {
    step "Checking prerequisites"

    # Check Ollama
    if command -v ollama &>/dev/null; then
        OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "unknown")
        success "Ollama found: $OLLAMA_VERSION"
    else
        error "Ollama not installed!"
        echo "    Install: curl -fsSL https://ollama.com/install.sh | sh"
        exit 1
    fi

    # Check if Ollama is running
    if curl -sf http://localhost:11434/api/tags &>/dev/null; then
        success "Ollama is running on localhost:11434"
    else
        error "Ollama is NOT running!"
        echo "    Start it with: ollama serve"
        exit 1
    fi

    # Check Python
    if command -v python3 &>/dev/null; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        success "Python3 found: $PYTHON_VERSION"
    else
        error "Python3 not installed!"
        exit 1
    fi

    # Check FastAPI/uvicorn for old proxy, we use stdlib now
    info "Using Python stdlib (no extra dependencies needed)"

    # Check Qwen CLI
    if command -v qwen &>/dev/null; then
        QWEN_VERSION=$(qwen --version 2>/dev/null || echo "unknown")
        success "Qwen Code CLI found: $QWEN_VERSION"
    else
        warn "Qwen Code CLI not found"
        echo "    Install: npm install -g @qwen-code/qwen-code"
        echo "    (You can still use the proxy with other clients)"
    fi
}

###############################################################################
# List available Ollama models
###############################################################################
list_models() {
    step "Available Ollama models"

    local models
    models=$(curl -sf http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    name = m['name']
    size = m.get('details', {}).get('parameter_size', '?')
    family = m.get('details', {}).get('family', '?')
    print(f'{name}  ({size} · {family})')
" 2>/dev/null)

    if [ -z "$models" ]; then
        warn "No models found. Pull one with: ollama pull qwen2.5-coder:14b"
        return 1
    fi

    echo "$models" | nl -ba
    echo ""
    return 0
}

###############################################################################
# Model selection
###############################################################################
select_model() {
    step "Select a model"

    # Get model list
    local model_list
    model_list=$(curl -sf http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(m['name'])
" 2>/dev/null)

    if [ -z "$model_list" ]; then
        error "No Ollama models available."
        echo "    Pull one: ollama pull qwen2.5-coder:14b"
        exit 1
    fi

    # Convert to array
    IFS=$'\n' read -d '' -ra MODELS <<< "$model_list" || true

    echo -e "  ${CYAN}Available models:${NC}"
    for i in "${!MODELS[@]}"; do
        echo -e "    ${GREEN}$((i+1))${NC}) ${MODELS[$i]}"
    done
    echo ""

    # Ask for selection
    if [ -t 0 ]; then
        # Interactive mode
        while true; do
            read -p "  Select model number (1-${#MODELS[@]}): " choice
            if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#MODELS[@]}" ]; then
                SELECTED_MODEL="${MODELS[$((choice-1))]}"
                success "Selected: $SELECTED_MODEL"
                break
            else
                error "Invalid selection. Enter a number between 1 and ${#MODELS[@]}"
            fi
        done
    else
        # Piped mode - auto-select first model
        SELECTED_MODEL="${MODELS[0]}"
        info "Auto-selected (piped mode): $SELECTED_MODEL"
    fi
}

###############################################################################
# Install proxy
###############################################################################
install_proxy() {
    step "Installing proxy"

    # Create install directory
    mkdir -p "$INSTALL_DIR"
    success "Created directory: $INSTALL_DIR"

    # Copy proxy script
    cp "$SCRIPT_DIR/ollama-proxy.py" "$INSTALL_DIR/ollama-proxy.py"
    chmod +x "$INSTALL_DIR/ollama-proxy.py"
    success "Installed proxy script"

    # Copy service manager
    cp "$SCRIPT_DIR/service.sh" "$INSTALL_DIR/service.sh"
    chmod +x "$INSTALL_DIR/service.sh"
    success "Installed service manager"

    # Copy model selector
    cp "$SCRIPT_DIR/model-selector.sh" "$INSTALL_DIR/model-selector.sh"
    chmod +x "$INSTALL_DIR/model-selector.sh"
    success "Installed model selector"
}

###############################################################################
# Configure Qwen Code CLI
###############################################################################
configure_qwen() {
    step "Configuring Qwen Code CLI"

    QWEN_SETTINGS="$HOME/.qwen/settings.json"

    if [ ! -f "$QWEN_SETTINGS" ]; then
        warn "Qwen Code settings not found at $QWEN_SETTINGS"
        echo "    Run Qwen Code once to generate settings, then re-run this installer."
        return 1
    fi

    # Backup existing settings
    cp "$QWEN_SETTINGS" "${QWEN_SETTINGS}.backup.$(date +%Y%m%d-%H%M%S)"
    success "Backed up existing settings"

    # Add/update the local model entry using Python for reliable JSON manipulation
    python3 << PYEOF
import json

settings_path = "$QWEN_SETTINGS"
with open(settings_path, 'r') as f:
    settings = json.load(f)

# Ensure modelProviders.openai exists
if "modelProviders" not in settings:
    settings["modelProviders"] = {}
if "openai" not in settings["modelProviders"]:
    settings["modelProviders"]["openai"] = []

providers = settings["modelProviders"]["openai"]

# Remove existing local model entry if present
providers = [p for p in providers if p.get("id") != "ollama-local"]

# Add our model entry
model_entry = {
    "id": "ollama-local",
    "name": "[Ollama Local] $SELECTED_MODEL",
    "baseUrl": "http://localhost:$PROXY_PORT/v1",
    "apiKey": "ollama",
    "generationConfig": {
        "contextWindowSize": 32768
    }
}
providers.insert(0, model_entry)

settings["modelProviders"]["openai"] = providers

# Set as default model
settings["model"] = {"name": "ollama-local"}

# Add timeout to model generationConfig (not deprecated contentGenerator)
if "model" not in settings:
    settings["model"] = {}
if "generationConfig" not in settings["model"]:
    settings["model"]["generationConfig"] = {}
settings["model"]["generationConfig"]["timeout"] = 120000

# Add timeout to local model
for p in providers:
    if p.get("id") == "ollama-local":
        if "generationConfig" not in p:
            p["generationConfig"] = {}
        p["generationConfig"]["timeout"] = 120000
        break

# Add OLLAMA_API_KEY to env if not present
if "env" not in settings:
    settings["env"] = {}
settings["env"]["OLLAMA_API_KEY"] = "ollama"

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
PYEOF

    success "Added model to Qwen Code settings"
    info "Model ID: ollama-local"
    info "Model Name: [Ollama Local] $SELECTED_MODEL"
    info "API Endpoint: http://localhost:$PROXY_PORT/v1"
}

###############################################################################
# Start proxy service
###############################################################################
start_proxy() {
    step "Starting proxy service"

    # Kill existing proxies (both old and new script names)
    pkill -f "ollama-proxy.py" 2>/dev/null && warn "Stopped ollama-proxy.py" || true
    pkill -f "qwen_api.py" 2>/dev/null && warn "Stopped qwen_api.py" || true
    sleep 2

    # Verify port is free
    if lsof -i :$PROXY_PORT &>/dev/null; then
        error "Port $PROXY_PORT is still in use"
        lsof -i :$PROXY_PORT
        exit 1
    fi

    # Create proxy config
    python3 -c "
import json
config = {'port': $PROXY_PORT, 'model': '$SELECTED_MODEL'}
with open('$INSTALL_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
    success "Created proxy config"

    # Start proxy in background
    nohup python3 "$INSTALL_DIR/ollama-proxy.py" \
        --port "$PROXY_PORT" \
        --model "$SELECTED_MODEL" \
        > "$PROXY_LOG" 2>&1 &

    # Wait for startup
    sleep 3

    if curl -sf "http://localhost:$PROXY_PORT/health" &>/dev/null; then
        success "Proxy started on port $PROXY_PORT"
        success "Model: $SELECTED_MODEL"
    else
        error "Proxy failed to start. Check log: $PROXY_LOG"
        cat "$PROXY_LOG"
        exit 1
    fi
}

###############################################################################
# Test tool calling
###############################################################################
test_tool_calling() {
    step "Testing tool calling"

    local response
    response=$(curl -s "http://localhost:$PROXY_PORT/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "test",
            "messages": [{"role": "user", "content": "List files in current directory"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                }
            }],
            "stream": false
        }' 2>/dev/null)

    local has_tool_calls
    has_tool_calls=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tc = data.get('choices', [{}])[0].get('message', {}).get('tool_calls', [])
    print('yes' if tc else 'no')
except:
    print('error')
" 2>/dev/null)

    if [ "$has_tool_calls" = "yes" ]; then
        success "Tool calling works! ✅"
    else
        warn "Tool calling test inconclusive (model may not support tools)"
        echo "    Response preview:"
        echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message'].get('content','')[:200])" 2>/dev/null || echo "    (parse error)"
    fi
}

###############################################################################
# Setup quick-start aliases
###############################################################################
setup_aliases() {
    step "Setting up quick-start commands"

    BASHRC="$HOME/.bashrc"

    # Create .env file for persistent config
    QWEN_ENV="$HOME/.qwen/.env"
    mkdir -p "$(dirname "$QWEN_ENV")"
    cat > "$QWEN_ENV" << 'EOF'
OLLAMA_API_KEY=ollama
EOF
    chmod 600 "$QWEN_ENV"
    success "Created Qwen .env file"

    # Add env var and aliases if not already present
    if ! grep -q "OLLAMA_API_KEY" "$BASHRC" 2>/dev/null; then
        cat << 'ALIASES' >> "$BASHRC"

# === Ollama-Qwen Proxy Quick Start ===
export OLLAMA_API_KEY="ollama"
alias ollama-qwen-start='bash ~/.ollama-qwen/service.sh start'
alias ollama-qwen-stop='bash ~/.ollama-qwen/service.sh stop'
alias ollama-qwen-restart='bash ~/.ollama-qwen/service.sh restart'
alias ollama-qwen-status='bash ~/.ollama-qwen/service.sh status'
alias ollama-qwen-models='bash ~/.ollama-qwen/service.sh models'
alias ollama-qwen-switch='bash ~/.ollama-qwen/service.sh switch'
alias ollama-qwen-logs='tail -f ~/.ollama-qwen/proxy.log'
# === End Ollama-Qwen ===
ALIASES
        success "Added OLLAMA_API_KEY and quick-start aliases to ~/.bashrc"
        info "Run 'source ~/.bashrc' or restart terminal to use"
    else
        info "Aliases already configured"
    fi
}

###############################################################################
# Summary
###############################################################################
show_summary() {
    step "Installation Complete!"

    echo -e "
  ${GREEN}✅ Proxy installed and running${NC}
  ${GREEN}✅ Qwen Code CLI configured${NC}
  ${GREEN}✅ Quick-start commands available${NC}

  ${CYAN}Quick Start Commands:${NC}
  ┌────────────────────────────────────────────────────────┐
  │  ollama-qwen-start    Start proxy                       │
  │  ollama-qwen-stop     Stop proxy                        │
  │  ollama-qwen-restart  Restart proxy                     │
  │  ollama-qwen-status   Check proxy status                │
  │  ollama-qwen-models   List available models             │
  │  ollama-qwen-switch   Switch to different model         │
  │  ollama-qwen-logs     View proxy logs                   │
  └────────────────────────────────────────────────────────┘

  ${CYAN}Run Qwen Code with local model:${NC}
  →  qwen -m ollama-local

  ${CYAN}Or switch model inside Qwen:${NC}
  →  /model  (then select ollama-local)

  ${CYAN}Proxy details:${NC}
  →  Endpoint: http://localhost:$PROXY_PORT/v1
  →  Model: $SELECTED_MODEL
  →  Log: $PROXY_LOG

  ${YELLOW}See README.md in the installer for full documentation.${NC}
"
}

###############################################################################
# Main
###############################################################################
main() {
    banner
    echo -e "  ${BLUE}This installer will:${NC}"
    echo "    1. Check prerequisites (Ollama, Python, Qwen CLI)"
    echo "    2. Let you select an Ollama model"
    echo "    3. Install the proxy bridge"
    echo "    4. Configure Qwen Code CLI"
    echo "    5. Start the proxy"
    echo "    6. Test tool calling"
    echo ""

    # Detect if running in interactive or piped mode
    if [ -t 0 ]; then
        # Interactive mode - read from terminal
        read -p "  Continue? (Y/n): " confirm
        if [[ "$confirm" =~ ^[Nn]$ ]]; then
            echo "  Aborted."
            exit 0
        fi
    else
        # Piped mode - auto-accept all prompts
        info "Running in non-interactive mode (piped input)"
        confirm="Y"
    fi

    check_prerequisites
    list_models || true
    select_model
    install_proxy
    configure_qwen || true
    start_proxy
    test_tool_calling
    setup_aliases
    show_summary
}

main "$@"
