# Ollama → Qwen Code CLI Bridge

Jalankan **semua model Ollama** di Qwen Code CLI dengan dukungan **full tool calling** (baca file, tulis file, edit, bash, dll). Zero-dependency, dioptimalkan untuk kecepatan.

## Quick Start

```bash
# 1. Install (pastikan Ollama sudah running)
cd ollama-qwen-installer
bash install.sh

# 2. Jalankan Qwen Code
source ~/.bashrc
qwen -m ollama-local --approval-mode yolo
```

## Prerequisites

| Software | Version | Install |
|---|---|---|
| **Ollama** | Latest | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **Python 3** | 3.8+ | Sudah ada di kebanyakan Linux |
| **Qwen Code CLI** | 0.15+ | `npm install -g @qwen-code/qwen-code` |

### Setup Ollama (jika belum)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model yang diinginkan
ollama pull qwen2.5-coder:1.5b    # FAST - daily coding
ollama pull qwen2.5-coder:14b     # BALANCED - complex tasks
ollama pull qwen3-coder:30b       # POWERFUL - heavy refactoring

# Pastikan Ollama running
ollama serve
```

## Installation

```bash
cd ollama-qwen-installer
bash install.sh
```

Installer akan:
1. Cek prerequisites (Ollama, Python, Qwen CLI)
2. Tampilkan model tersedia dengan speed rating
3. Pilih model
4. Pilih performance preset (Fast/Balanced/Powerful)
5. Install optimized proxy bridge
6. Konfigurasi Qwen Code CLI
7. Start proxy
8. Test tool calling
9. Setup quick-start aliases

## Quick Commands

Setelah install, alias ini tersedia di `~/.bashrc`:

| Command | Fungsi |
|---|---|
| `ollama-qwen-start` | Start proxy |
| `ollama-qwen-stop` | Stop proxy |
| `ollama-qwen-restart` | Restart proxy |
| `ollama-qwen-status` | Cek status proxy |
| `ollama-qwen-models` | List model + speed rating |
| `ollama-qwen-switch` | Switch model (interactive) |
| `ollama-qwen-ctx` | Adjust context size (speed tuning) |
| `ollama-qwen-logs` | Follow proxy logs |

## Running Qwen Code

```bash
# Basic - auto-approve semua actions
qwen -m ollama-local --approval-mode yolo

# Dengan prompt langsung
echo "Buat file index.html dengan Bootstrap 5" | qwen -m ollama-local -y

# Interactive mode
qwen -m ollama-local
# Lalu ketik perintah di interactive prompt
```

### Approval Modes

| Mode | Deskripsi |
|---|---|
| `yolo` | Auto-approve semua actions (recommended untuk local model) |
| `auto-edit` | Auto-approve edit tools only, prompt untuk bash |
| `default` | Prompt untuk semua actions |
| `plan` | Plan only, tidak execute |

## Model Recommendations

| Model | RAM | Speed | Best For |
|---|---|---|---|
| `qwen2.5-coder:1.5b` | ~1 GB | ⚡⚡⚡ 2-3s | **Daily tasks** - buat file, baca code, simple edits |
| `qwen2.5-coder:14b` | ~9 GB | ⚡⚡ 5-8s | **Complex tasks** - refactoring, architecture, debugging |
| `qwen3-coder:30b` | ~18 GB | ⚡ 10-15s | **Heavy tasks** - large refactors, code generation |

### Switch Model

```bash
# Interactive switch
ollama-qwen-switch

# Manual: edit settings
# Model akan tampil di Qwen sebagai "ollama-local"
```

## Performance Tuning

### Context Size (num_ctx)

Smaller = lebih cepat, Larger = lebih banyak context

```bash
# Check current setting
ollama-qwen-ctx

# Set context size
ollama-qwen-ctx 4096    # Fast (recommended for 1.5b)
ollama-qwen-ctx 8192    # Balanced (recommended for 14b)
ollama-qwen-ctx 16384   # Powerful (recommended for 30b+)
```

### Performance Presets (saat install)

| Preset | num_ctx | keep_alive | Model |
|---|---|---|---|
| **Fast** | 4096 | 5m | 1.5b |
| **Balanced** | 8192 | 10m | 14b |
| **Powerful** | 16384 | 30m | 30b+ |

## Available Tools

Setelah proxy berjalan, model Ollama bisa menggunakan semua tools ini:

| Tool | Fungsi | Contoh Use Case |
|---|---|---|
| `read_file` | Baca isi file | Baca source code, config files |
| `write_file` | Tulis/buat file baru | Buat HTML, Python, JS files |
| `edit` | Edit file (search & replace) | Ubah fungsi spesifik di file |
| `run_shell_command` | Jalankan shell command | `mkdir`, `git`, `npm`, `python` |
| `list_directory` | List isi folder | Lihat struktur project |
| `glob` | Cari file by pattern | `**/*.ts`, `src/**/*.py` |
| `grep_search` | Cari teks di file | Cari fungsi/variabel |
| `web_fetch` | Ambil konten web | Baca dokumentasi online |
| `todo_write` | Task management | Track progress tasks |
| `agent` | Launch sub-agent | Parallel tasks |

### Contoh Penggunaan

```
> Buatkan file index.html dengan Bootstrap 5 dan navbar responsive

> Baca semua file di folder src/ dan jelaskan strukturnya

> Edit file app.py untuk menambahkan endpoint /api/users

> Jalankan npm install lalu build project ini

> Cari semua fungsi yang mengandung "auth" di codebase

> Buat folder structure untuk project React baru
```

## Architecture

```
Qwen Code CLI ──(OpenAI API)──▶ Proxy (port 8001) ──(Ollama API)──▶ Ollama (port 11434)
                      │                                                    │
                      │ ◀── tool_calls format ── Transform ── ◀── content │
```

1. Qwen Code mengirim request OpenAI-compatible ke proxy
2. Proxy meneruskan ke Ollama dengan optimizations (num_ctx, keep_alive)
3. Ollama mengembalikan tool call dalam `content` sebagai JSON
4. Proxy transform `content` → `tool_calls` format OpenAI proper
5. Qwen Code menerima dan mengeksekusi tool calls

## Project Structure

```
ollama-qwen-installer/
├── README.md              # Dokumentasi ini
├── install.sh             # One-click installer
├── ollama-proxy.py        # Proxy server (optimized, zero-deps)
├── service.sh             # Service manager
└── model-selector.sh      # Interactive model selector

~/.ollama-qwen/            # Installed directory
├── ollama-proxy.py        # Proxy script
├── service.sh             # Service manager
├── model-selector.sh      # Model selector
├── config.json            # Proxy config (port, model, num_ctx, keep_alive)
└── proxy.log              # Log file
```

## Troubleshooting

### Proxy tidak bisa start

```bash
# Cek apakah Ollama running
ollama list

# Cek apakah port sudah dipakai
lsof -i :8001

# Cek log
ollama-qwen-logs
```

### "Missing credentials for modelProviders"

```bash
# Pastikan env var sudah set
export OLLAMA_API_KEY="ollama"

# Atau cek .env file
cat ~/.qwen/.env
# Harus berisi: OLLAMA_API_KEY=ollama
```

### Response terlalu lama / timeout

```bash
# Kurangi context size (lebih cepat)
ollama-qwen-ctx 4096

# Atau pilih model lebih kecil
ollama-qwen-switch qwen2.5-coder:1.5b
```

### Model tidak muncul di daftar

```bash
# Refresh model Ollama
ollama pull <model-name>

# Cek model tersedia
ollama-qwen-models
```

### Tool calling tidak bekerja

```bash
# Test proxy langsung
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"hi"}],"tools":[{"type":"function","function":{"name":"echo","parameters":{"type":"object","properties":{"msg":{"type":"string"}},"required":["msg"]}}}],"stream":false}'

# Harusnya ada "tool_calls" di response
```

### Qwen Code tidak bisa connect

```bash
# Cek settings
python3 -c "import json;s=json.load(open('~/.qwen/settings.json'));print([p for p in s['modelProviders']['openai'] if p['id']=='ollama-local'])"

# Restart proxy
ollama-qwen-restart

# Re-run Qwen
qwen -m ollama-local --approval-mode yolo
```

### Out of memory

```bash
# Pilih model lebih kecil
ollama-qwen-switch qwen2.5-coder:1.5b

# Atau kurangi context
ollama-qwen-ctx 2048
```

## Manual Proxy Usage

### Start Manual

```bash
# Default (client pilih model)
python3 ~/.ollama-qwen/ollama-proxy.py

# Force model tertentu
python3 ~/.ollama-qwen/ollama-proxy.py --model qwen2.5-coder:1.5b

# Custom port + optimizations
python3 ~/.ollama-qwen/ollama-proxy.py --port 9000 --num-ctx 4096 --keep-alive 5m
```

### API Endpoints

```bash
# Health check
curl http://localhost:8001/health

# List models
curl http://localhost:8001/v1/models

# Chat (non-streaming)
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hello"}],"stream":false}'

# Chat (streaming)
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hello"}],"stream":true}'

# Tool calling
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Create test.txt"}],
    "tools": [{"type":"function","function":{"name":"write_file","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}}],
    "stream": false
  }'
```

## Using with Other Clients

Proxy menggunakan OpenAI-compatible API, jadi bisa dipakai dengan client lain:

### OpenAI SDK (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="ollama"
)

response = client.chat.completions.create(
    model="qwen2.5-coder:1.5b",
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...],
    stream=False
)
```

### curl

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{"model":"qwen2.5-coder:1.5b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## Optimizations

Proxy ini sudah dioptimalkan untuk performa maksimal:

| Optimization | Deskripsi |
|---|---|
| **num_ctx tuning** | Context window lebih kecil = response lebih cepat |
| **keep_alive** | Model tetap loaded di memory, tidak perlu reload tiap request |
| **Zero dependencies** | Hanya pakai Python stdlib, tidak perlu install package tambahan |
| **Threaded server** | Handle multiple requests secara concurrent |
| **Minimal logging** | Tidak ada overhead logging yang tidak perlu |
| **Smart parsing** | Tool call extraction yang optimized, tidak parse unnecessary content |

## License & Credits

- **Ollama**: https://ollama.com
- **Qwen Code CLI**: https://github.com/qwen-code
- **Proxy**: Custom bridge server (Python stdlib, zero dependencies)

## Test Results (Latest)

| Test | Status |
|---|---|
| Proxy Health | ✅ OK |
| Model List | ✅ 6 models |
| Chat (no tools) | ✅ Working |
| Tool Calling (write_file) | ✅ Working |
| Model Mapping (ollama-local) | ✅ Working |
| Qwen Code CLI - Create File | ✅ Working |
| Qwen Code CLI - Read File | ✅ Working |
| Streaming (SSE) | ✅ Working |
