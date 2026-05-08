#!/usr/bin/env python3
"""Ollama-to-OpenAI Proxy - Stable stdlib version"""
import json, logging, sys, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

OLLAMA = "http://localhost:11434"
MODEL_MAP = {"ollama-local": "qwen2.5-coder:14b", "ollama": "qwen2.5-coder:14b"}

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
logger = logging.getLogger("proxy")

def resolve_model(name):
    return MODEL_MAP.get(name, name)

def extract_tool_calls(content):
    if not content: return []
    content = content.strip()
    if content.startswith('{'):
        try:
            d = json.loads(content, strict=False)
            if isinstance(d, dict) and "name" in d and "arguments" in d: return [d]
            if isinstance(d, list): return d
        except: pass
    s = content.find('{')
    if s == -1: return []
    depth = 0
    for i, ch in enumerate(content[s:], s):
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    d = json.loads(content[s:i+1], strict=False)
                    if isinstance(d, dict) and "name" in d and "arguments" in d: return [d]
                    if isinstance(d, list): return d
                except: pass
                break
    return []

def transform(data):
    try:
        choices = data.get("choices", [])
        if not choices: return data
        msg = choices[0].get("message", {})
        parsed = extract_tool_calls(msg.get("content", ""))
        if parsed:
            tc = []
            for i, c in enumerate(parsed):
                if isinstance(c, dict) and "name" in c:
                    args = c.get("arguments", c.get("parameters", {}))
                    if isinstance(args, dict): args = json.dumps(args)
                    elif not isinstance(args, str): args = str(args)
                    tc.append({"id": f"call_{i:04d}", "type": "function", "function": {"name": c["name"], "arguments": args}})
            if tc:
                msg["tool_calls"] = tc
                msg["content"] = None
    except Exception as e:
        logger.error(f"Transform error: {e}")
    return data

def ollama_req(path, body=None):
    url = f"{OLLAMA}{path}"
    data = None
    if body:
        body = body.copy()
        body["model"] = resolve_model(body.get("model", "qwen2.5-coder:14b"))
        data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="POST" if body else "GET")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except URLError as e:
        return 502, {"error": f"Ollama error: {e.reason}"}
    except Exception as e:
        return 500, {"error": str(e)}

def send_json(h, status, data):
    body = json.dumps(data).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Connection", "keep-alive")
    h.end_headers()
    h.wfile.write(body)

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): logger.info(fmt % args)

    def do_GET(self):
        if "/models" in self.path or self.path in ("/health", "/"):
            st, d = ollama_req("/api/tags")
            if st == 200:
                ms = [{"id": m["name"], "object": "model", "created": 0, "owned_by": m.get("details",{}).get("family","?")} for m in d.get("models",[])]
                send_json(self, 200, {"object": "list", "data": ms})
            else:
                send_json(self, 200, {"object": "list", "data": []})
        else:
            send_json(self, 404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            try:
                ln = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(ln))
            except Exception as e:
                send_json(self, 400, {"error": str(e)}); return
            st, d = ollama_req("/v1/chat/completions", body)
            if st != 200:
                send_json(self, st, d); return
            d = transform(d)
            if body.get("stream"):
                self._sse(d)
            else:
                send_json(self, 200, d)
        else:
            send_json(self, 404, {"error": "Not found"})

    def _sse(self, data):
        try:
            mid = data.get("id", "p")
            model = data.get("model", "m")
            msg = data["choices"][0]["message"]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            chunks = []
            if msg.get("tool_calls"):
                tc = [{"id": f"call_{i}", "type": "function", "function": t["function"], "index": i} for i, t in enumerate(msg["tool_calls"])]
                chunks.append({"id": mid, "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": tc}, "finish_reason": None}]})
            elif msg.get("content"):
                chunks.append({"id": mid, "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "content": msg["content"]}, "finish_reason": None}]})
            chunks.append({"id": mid, "object": "chat.completion.chunk", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            for c in chunks:
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as e:
            logger.error(f"Stream error: {e}")

class TS(HTTPServer):
    def process_request(self, req, addr):
        threading.Thread(target=self._h, args=(req, addr), daemon=True).start()
    def _h(self, req, addr):
        try: self.finish_request(req, addr)
        except: self.handle_error(req, addr)
        finally: self.shutdown_request(req)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    model = sys.argv[2] if len(sys.argv) > 2 else None
    if model: MODEL_MAP["default"] = model
    s = TS(("0.0.0.0", port), H)
    print(f"Proxy on port {port}, model: {model or 'client-specified'}", flush=True)
    try: s.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped."); s.shutdown()
