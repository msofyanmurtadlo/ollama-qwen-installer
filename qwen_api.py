#!/usr/bin/env python3
import json, logging, sys, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

OLLAMA = "http://localhost:11434"
MODEL_MAP = {"ollama-local": "qwen2.5-coder:14b", "ollama": "qwen2.5-coder:14b"}
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("proxy")

def resolve_model(name):
    return MODEL_MAP.get(name, name)

# Tools to NOT transform from content JSON to tool_calls.
# These are interactive tools that Qwen Code handles differently.
# Let the model output them as content instead of triggering tool execution.
SKIP_TOOLS = {"ask_user_question", "todo_write", "exit_plan_mode"}

def extract_tool_call(content):
    if not content: return None
    content = content.strip()
    if content.startswith("{"):
        try:
            d = json.loads(content, strict=False)
            if isinstance(d, dict) and "name" in d and "arguments" in d:
                # Skip interactive tools - let them render as content
                if d["name"] in SKIP_TOOLS:
                    return None
                args = d["arguments"]
                if isinstance(args, dict): args = json.dumps(args)
                return {"id": "call_0000", "type": "function", "function": {"name": d["name"], "arguments": args}}
        except: pass
    s = content.find("{")
    if s == -1: return None
    depth = 0
    for i, ch in enumerate(content[s:], s):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    d = json.loads(content[s:i+1], strict=False)
                    if isinstance(d, dict) and "name" in d and "arguments" in d:
                        args = d["arguments"]
                        if isinstance(args, dict): args = json.dumps(args)
                        return {"id": "call_0000", "type": "function", "function": {"name": d["name"], "arguments": args}}
                except: pass
                break
    return None

def ensure_tool_calls(data, has_tools=False):
    for ch in data.get("choices", []):
        msg = ch.get("message", {})
        if has_tools and not msg.get("tool_calls") and msg.get("content"):
            tc = extract_tool_call(msg["content"])
            if tc:
                msg["tool_calls"] = [tc]
                msg["content"] = None
                ch["finish_reason"] = "tool_calls"
        for t in msg.get("tool_calls", []):
            fn = t.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, dict): fn["arguments"] = json.dumps(args)
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
            stream = body.get("stream", False)
            body["stream"] = False
            has_tools = bool(body.get("tools"))
            st, d = ollama_req("/v1/chat/completions", body)
            if st != 200:
                send_json(self, st, d); return
            d = ensure_tool_calls(d, has_tools)
            if stream:
                self._sse(d)
            else:
                send_json(self, 200, d)
        else:
            send_json(self, 404, {"error": "Not found"})
    def _sse(self, data):
        try:
            mid = data.get("id", "p"); mod = data.get("model", "m")
            msg = data["choices"][0]["message"]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            chunks = []
            if msg.get("tool_calls"):
                tc = [{"id": "call_%d" % i, "type": "function", "function": t["function"], "index": i} for i, t in enumerate(msg["tool_calls"])]
                chunks.append({"id": mid, "object": "chat.completion.chunk", "model": mod, "choices": [{"index": 0, "delta": {"role": "assistant", "tool_calls": tc}, "finish_reason": None}]})
            elif msg.get("content"):
                chunks.append({"id": mid, "object": "chat.completion.chunk", "model": mod, "choices": [{"index": 0, "delta": {"role": "assistant", "content": msg["content"]}, "finish_reason": None}]})
            else:
                chunks.append({"id": mid, "object": "chat.completion.chunk", "model": mod, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
            chunks.append({"id": mid, "object": "chat.completion.chunk", "model": mod, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            for c in chunks:
                line = "data: " + json.dumps(c) + "\n\n"
                self.wfile.write(line.encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
        except Exception as e: logger.error(f"Stream error: {e}")

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
    print("Proxy on port %d" % port, flush=True)
    try: s.serve_forever()
    except KeyboardInterrupt: print("Stopped."); s.shutdown()
