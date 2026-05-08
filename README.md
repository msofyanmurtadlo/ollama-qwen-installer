# Ollama → Qwen Code CLI Tool Calling Bridge

Jalankan **semua model Ollama** di Qwen Code CLI dengan dukungan **full tool calling** (baca file, tulis file, edit, shell command, dll).

## 📋 Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| **Ollama** | Latest | Local model runtime |
| **Python 3** | 3.8+ | Proxy server (stdlib only) |
| **Qwen Code CLI** | 0.15+ | AI coding assistant |

### Install jika belum ada:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model (contoh)
ollama pull qwen2.5-coder:14b
ollama pull qwen3-coder:30b

# Install Qwen Code CLI (jika belum)
npm install -g @qwen-code/qwen-code
```

---

## 🚀 Quick Start — One Click Install

```bash
cd /home/dev/ollama-qwen-installer
bash install.sh
```

Installer akan:
1. ✅ Cek prerequisites (Ollama, Python, Qwen CLI)
2. 📋 Tampilkan model yang tersedia
3. 🎯 Minta pilih model
4. 📦 Install proxy bridge
5. ⚙️ Konfigurasi Qwen Code CLI
6. ▶️ Start proxy
7. 🧪 Test tool calling
8. 🔗 Setup quick-start aliases

Setelah install, jalankan:

```bash
# Source aliases (atau restart terminal)
source ~/.bashrc

# Start proxy
ollama-qwen-start

# Jalankan Qwen Code
qwen -m ollama-local
```

---

## 📁 Struktur File

```
/home/dev/ollama-qwen-installer/
├── README.md              # Dokumentasi ini
├── install.sh             # One-click installer
├── ollama-proxy.py        # Proxy server (Ollama → OpenAI format)
├── service.sh             # Service manager (start/stop/restart)
└── model-selector.sh      # Interactive model selector

~/.ollama-qwen/            # Install directory (setelah install)
├── ollama-proxy.py        # Proxy script
├── service.sh             # Service manager
├── config.json            # Proxy config (port + model)
└── proxy.log              # Log file
```

---

## 🔧 Quick-Start Commands

Setelah install, alias ini tersedia di `~/.bashrc`:

| Command | Fungsi |
|---|---|
| `ollama-qwen-start` | Start proxy |
| `ollama-qwen-stop` | Stop proxy |
| `ollama-qwen-restart` | Restart proxy |
| `ollama-qwen-status` | Cek status proxy |
| `ollama-qwen-models` | List model Ollama |
| `ollama-qwen-switch` | Switch model (interactive) |
| `ollama-qwen-logs` | Follow proxy logs |

---

## 🎯 Cara Pakai

### 1. Start Proxy

```bash
ollama-qwen-start
```

### 2. Jalankan Qwen Code

```bash
qwen -m ollama-local
```

Atau switch model di dalam Qwen Code session:
```
/model
```
Lalu pilih `ollama-local`.

### 3. Switch Model

```bash
# Interactive
ollama-qwen-switch

# Langsung ke model tertentu
ollama-qwen-switch qwen3-coder:30b
```

### 4. Cek Status

```bash
ollama-qwen-status
```

### 5. Lihat Logs

```bash
ollama-qwen-logs
```

---

## 🛠️ Available Tools di Qwen Code CLI

Setelah proxy berjalan, model Ollama bisa menggunakan semua tools ini:

| Tool | Fungsi | Contoh |
|---|---|---|
| `read_file` | Baca isi file | Baca source code |
| `write_file` | Tulis/membuat file baru | Buat file HTML, Python, dll |
| `edit` | Edit file (search & replace) | Ubah fungsi spesifik di file |
| `run_shell_command` | Jalankan shell command | `mkdir`, `git`, `npm`, dll |
| `list_directory` | List isi folder | Lihat struktur project |
| `glob` | Cari file by pattern | `**/*.ts`, `src/**/*.py` |
| `grep_search` | Cari teks di file | Cari fungsi/variabel |
| `web_fetch` | Ambil konten web | Baca dokumentasi online |
| `todo_write` | Task management | Track progress |
| `agent` | Launch sub-agent | Parallel tasks |

### Contoh Penggunaan di Qwen Code:

```
> Buat file index.html dengan Bootstrap 5 dan navbar responsive
> Baca semua file di folder src/ dan jelaskan strukturnya
> Edit file app.py untuk menambahkan endpoint /api/users
> Jalankan npm install lalu build project ini
> Cari semua fungsi yang mengandung "auth" di codebase
```

---

## ⚙️ Konfigurasi Manual

### Proxy Config

File: `~/.ollama-qwen/config.json`

```json
{
  "port": 8001,
  "model": "qwen2.5-coder:14b"
}
```

| Field | Default | Keterangan |
|---|---|---|
| `port` | 8001 | Port proxy server |
| `model` | (kosong) | Model default (kosong = client yang pilih) |

### Jalankan Proxy Manual

```bash
# Default (client pilih model)
python3 ~/.ollama-qwen/ollama-proxy.py

# Force model tertentu
python3 ~/.ollama-qwen/ollama-proxy.py --model qwen3-coder:30b

# Custom port
python3 ~/.ollama-qwen/ollama-proxy.py --port 9000

# Custom Ollama URL
python3 ~/.ollama-qwen/ollama-proxy.py --ollama-url http://192.168.1.100:11434
```

### Test Proxy

```bash
# Health check
curl http://localhost:8001/health

# List models
curl http://localhost:8001/v1/models

# Test chat
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hello"}],"stream":false}'

# Test tool calling
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"qwen2.5-coder:14b",
    "messages":[{"role":"user","content":"Buat file test.txt"}],
    "tools":[{"type":"function","function":{"name":"write_file","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}}],
    "stream":false
  }'
```

---

## 🏗️ Cara Kerja

```
Qwen Code CLI ──(OpenAI API)──▶ Proxy (port 8001) ──(Ollama API)──▶ Ollama (port 11434)
                      │                                                    │
                      │ ◀── tool_calls format ── Transform ── ◀── content │
```

1. **Qwen Code** mengirim request dengan format OpenAI-compatible ke proxy
2. **Proxy** meneruskan ke Ollama API
3. **Ollama** mengembalikan tool call dalam `content` sebagai JSON string
4. **Proxy** mengubah `content` → `tool_calls` format OpenAI yang proper
5. **Qwen Code** menerima tool calls dan mengeksekusinya

---

## 🐛 Troubleshooting

### Proxy tidak bisa start

```bash
# Cek apakah Ollama running
ollama list

# Cek apakah port sudah dipakai
lsof -i :8001

# Cek log
tail -f ~/.ollama-qwen/proxy.log
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
# Test langsung
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"qwen2.5-coder:14b",
    "messages":[{"role":"user","content":"List files in /tmp"}],
    "tools":[{"type":"function","function":{"name":"list_dir","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}],
    "stream":false
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['choices'][0]['message'],indent=2))"
```

Harusnya output `tool_calls` field.

### Qwen Code tidak bisa connect

```bash
# Cek settings
cat ~/.qwen/settings.json | python3 -m json.tool | grep -A5 "ollama-local"

# Restart proxy
ollama-qwen-restart

# Re-run Qwen Code
qwen -m ollama-local
```

### Out of memory / model terlalu besar

```bash
# Pilih model yang lebih kecil
ollama-qwen-switch qwen2.5-coder:1.5b

# Cek penggunaan RAM
ollama list
```

---

## 📊 Rekomendasi Model

| Model | RAM | Speed | Quality | Best For |
|---|---|---|---|---|
| `qwen2.5-coder:1.5b` | ~1 GB | ⚡⚡⚡ | ⭐⭐ | Quick tasks, testing |
| `qwen2.5-coder:14b` | ~9 GB | ⚡⚡ | ⭐⭐⭐⭐ | **Recommended** — best balance |
| `qwen3-coder:30b` | ~18 GB | ⚡ | ⭐⭐⭐⭐⭐ | Complex tasks, heavy refactoring |

---

## 🔌 Integrasi dengan AI Clients Lain

Proxy ini menggunakan OpenAI-compatible API, jadi bisa dipakai dengan client lain:

### OpenAI SDK (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="ollama"
)

response = client.chat.completions.create(
    model="qwen2.5-coder:14b",
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...]
)
```

### curl

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

---

## 📝 License & Credits

- **Ollama**: https://ollama.com
- **Qwen Code CLI**: https://github.com/qwen-code
- **Proxy**: Custom bridge server (Python stdlib, no dependencies)

Proxy ini **tidak memerlukan FastAPI/uvicorn** — menggunakan Python stdlib `http.server` sehingga zero-dependency.

---

## 🆘 Support

- Issue: Cek log di `~/.ollama-qwen/proxy.log`
- Status: `ollama-qwen-status`
- Health: `curl http://localhost:8001/health`
