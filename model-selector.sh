#!/bin/bash
###############################################################################
# Ollama-Qwen Model Selector
# Interactive model selection with preview
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

INSTALL_DIR="$HOME/.ollama-qwen"

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $1"; }
error()   { echo -e "${RED}[ERR]${NC}    $1"; }

echo -e "\n${CYAN}╔══════════════════════════════════════════════════╗"
echo -e "║  ${MAGENTA}Ollama Model Selector${CYAN}                              ║"
echo -e "╚══════════════════════════════════════════════════╝${NC}\n"

# Check Ollama
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    error "Ollama is not running"
    echo "    Start with: ollama serve"
    exit 1
fi

# Fetch and parse models
MODELS_INFO=$(curl -sf http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('models', [])
if not models:
    sys.exit(0)
for m in models:
    name = m['name']
    size = m.get('details', {}).get('parameter_size', '?')
    family = m.get('details', {}).get('family', '?')
    quant = m.get('details', {}).get('quantization_level', '?')
    print(f'{name}|{size}|{family}|{quant}')
" 2>/dev/null)

if [ -z "$MODELS_INFO" ]; then
    error "No Ollama models available"
    echo "    Pull one: ollama pull qwen2.5-coder:14b"
    exit 1
fi

# Display models
echo -e "  ${CYAN}Available Models:${NC}\n"
echo -e "  ${BLUE}No.${NC}  ${CYAN}Model Name${NC}  |  ${BLUE}Size${NC}  |  ${BLUE}Family${NC}  |  ${BLUE}Quant${NC}"
echo "  ──────────────────────────────────────────────────────────────"

IFS=$'\n' read -d '' -ra MODEL_LINES <<< "$MODELS_INFO"
declare -a MODEL_NAMES

for i in "${!MODEL_LINES[@]}"; do
    IFS='|' read -r name size family quant <<< "${MODEL_LINES[$i]}"
    MODEL_NAMES[$i]="$name"
    printf "  ${GREEN}%2d${NC}   %-30s  %6s  %8s  %s\n" "$((i+1))" "$name" "$size" "$family" "$quant"
done
echo ""

# Current model
CURRENT_MODEL=""
CONFIG_FILE="$INSTALL_DIR/config.json"
if [ -f "$CONFIG_FILE" ]; then
    CURRENT_MODEL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('model',''))" 2>/dev/null)
fi

if [ -n "$CURRENT_MODEL" ]; then
    echo -e "  ${CYAN}Current model:${NC} ${GREEN}$CURRENT_MODEL${NC}\n"
fi

# Selection
while true; do
    read -p "  Select model number (or 'q' to quit): " choice
    if [[ "$choice" == "q" ]]; then
        echo "  Aborted."
        exit 0
    fi
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#MODEL_NAMES[@]}" ]; then
        SELECTED="${MODEL_NAMES[$((choice-1))]}"
        break
    else
        error "Invalid selection. Enter 1-${#MODEL_NAMES[@]}"
    fi
done

echo ""
success "Selected: $SELECTED"

# Apply
read -p "  Switch to this model now? (Y/n): " confirm
if [[ ! "$confirm" =~ ^[Nn]$ ]]; then
    echo ""

    # Save config
    mkdir -p "$INSTALL_DIR"
    python3 -c "
import json
config = {'port': 8001, 'model': '$SELECTED'}
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
"
    success "Config saved"

    # Restart proxy if running
    if pgrep -f "ollama-proxy.py" &>/dev/null; then
        info "Restarting proxy with new model..."
        bash "$INSTALL_DIR/service.sh" restart
    else
        info "Proxy is not running. Start with: ollama-qwen-start"
    fi

    # Update Qwen settings
    QWEN_SETTINGS="$HOME/.qwen/settings.json"
    if [ -f "$QWEN_SETTINGS" ]; then
        python3 << PYEOF
import json

settings_path = "$QWEN_SETTINGS"
with open(settings_path, 'r') as f:
    settings = json.load(f)

providers = settings.get("modelProviders", {}).get("openai", [])

# Update local model name
for p in providers:
    if p.get("id") == "ollama-local":
        p["name"] = "[Ollama Local] $SELECTED"
        break

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
PYEOF
        success "Updated Qwen Code settings"
    fi

    echo ""
    echo -e "  ${GREEN}✅ Model switched to: $SELECTED${NC}"
    echo -e "  ${CYAN}Run:${NC} qwen -m ollama-local"
else
    echo "  Config not saved."
fi
