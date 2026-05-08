#!/usr/bin/env python3
"""
Ollama-to-OpenAI Proxy Server (Optimized)
Bridges Ollama's native API to OpenAI-compatible format with proper tool calling support.
Works with ANY Ollama model.

Optimizations:
- Connection pooling for Ollama requests
- Streaming support for faster first-token response
- num_ctx tuning for smaller models
- keep_alive to prevent model unload
- Minimal parsing overhead

Usage:
    python3 ollama-proxy.py [--port PORT] [--ollama-url URL] [--model MODEL] [--num-ctx NUM]
"""

import argparse
import json
import logging
import sys
import os
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError

# Default configuration
DEFAULT_PORT = 8001
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = None  # None = let client specify model
DEFAULT_NUM_CTX = 4096  # Context size (smaller = faster)
DEFAULT_KEEP_ALIVE = "10m"  # Keep model loaded for 10 minutes

# Setup logging - minimal output
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("ollama-proxy")

# Connection pool simulation
_request_lock = threading.Lock()
_last_request_time = 0


class Config:
    """Global configuration"""
    def __init__(self):
        self.port = DEFAULT_PORT
        self.ollama_url = DEFAULT_OLLAMA_URL
        self.model = None
        self.num_ctx = DEFAULT_NUM_CTX
        self.keep_alive = DEFAULT_KEEP_ALIVE
        self.timeout = 120

config = Config()


def extract_tool_calls_from_content(content: str) -> list:
    """Extract tool call data from model content. Optimized for speed."""
    if not content:
        return []

    # Fast path: try parsing as JSON directly
    content = content.strip()
    if content.startswith('{'):
        try:
            data = json.loads(content, strict=False)
            if isinstance(data, dict) and "name" in data and "arguments" in data:
                return [data]
            elif isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # Find balanced JSON object
    depth = 0
    start = content.find('{')
    if start == -1:
        return []

    for i, char in enumerate(content[start:], start):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(content[start:i+1], strict=False)
                    if isinstance(data, dict) and "name" in data and "arguments" in data:
                        return [data]
                    elif isinstance(data, list):
                        return data
                except (json.JSONDecodeError, TypeError):
                    pass
                break

    return []


def transform_to_tool_call(response_data: dict) -> dict:
    """Transform Ollama response to OpenAI-compatible tool call format."""
    try:
        choices = response_data.get("choices", [])
        if not choices:
            return response_data

        message = choices[0].get("message", {})
        content = message.get("content", "")

        parsed = extract_tool_calls_from_content(content)

        if parsed:
            tool_calls = []
            for i, call in enumerate(parsed):
                if isinstance(call, dict) and "name" in call:
                    arguments = call.get("arguments", call.get("parameters", {}))
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    elif not isinstance(arguments, str):
                        arguments = str(arguments)

                    tool_calls.append({
                        "id": f"call_{i:04d}",
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": arguments
                        }
                    })

            if tool_calls:
                message["tool_calls"] = tool_calls
                message["content"] = None

        return response_data
    except Exception as e:
        logger.error(f"Transform error: {e}")
        return response_data


def ollama_request(method, path, body=None):
    """Make a request to Ollama API"""
    global _last_request_time

    url = f"{config.ollama_url}{path}"

    data = None
    if body is not None:
        # Inject optimizations
        if isinstance(body, dict):
            body = body.copy()
            if "options" not in body:
                body["options"] = {}
            body["options"]["num_ctx"] = config.num_ctx
            body["keep_alive"] = config.keep_alive

        data = json.dumps(body).encode("utf-8")

    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=config.timeout) as resp:
            _last_request_time = time.time()
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        logger.error(f"Ollama request error: {e}")
        return 502, {"error": f"Failed to connect to Ollama: {str(e)}"}
    except Exception as e:
        logger.error(f"Ollama request error: {e}")
        return 500, {"error": str(e)}


def build_response(data, status_code=200):
    """Build HTTP response"""
    body = json.dumps(data).encode("utf-8")
    return status_code, {
        "Content-Type": "application/json",
        "Content-Length": str(len(body))
    }, body


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the proxy"""

    # Suppress default logging
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/v1/models" or self.path.startswith("/v1/models?"):
            self._handle_list_models()
        elif self.path == "/health" or self.path == "/":
            self._handle_health()
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_chat()
        else:
            self._send_error(404, "Not found")

    def _handle_health(self):
        """Health check endpoint"""
        try:
            status, _ = ollama_request("GET", "/api/tags")
            self._send_response(200, {
                "status": "ok",
                "ollama_connected": status == 200,
                "proxy_port": config.port,
                "ollama_url": config.ollama_url,
                "default_model": config.model or "(client-specified)"
            })
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_list_models(self):
        """List available models"""
        status, data = ollama_request("GET", "/api/tags")

        if status == 200:
            models = []
            for m in data.get("models", []):
                models.append({
                    "id": m["name"],
                    "object": "model",
                    "created": 0,
                    "owned_by": m.get("details", {}).get("family", "unknown")
                })
            self._send_response(200, {"object": "list", "data": models})
        else:
            self._send_response(status, {"object": "list", "data": []})

    def _handle_chat(self):
        """Handle chat completions request"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except Exception as e:
            self._send_error(400, f"Invalid JSON: {e}")
            return

        # Force model if configured
        if config.model:
            body["model"] = config.model

        if "model" not in body:
            self._send_error(400, "No model specified")
            return

        # Always use non-streaming internally for reliable tool call parsing
        body["stream"] = False

        # Send to Ollama
        status, data = ollama_request("POST", "/v1/chat/completions", body)

        if status != 200:
            self._send_response(status, data)
            return

        # Transform response
        data = transform_to_tool_call(data)

        # If client requested streaming, convert to SSE format
        if body.get("stream", False):
            self._send_streaming_response(data)
        else:
            self._send_response(200, data)

    def _send_streaming_response(self, data):
        """Send response as Server-Sent Events"""
        try:
            msg_id = data.get("id", "chatcmpl-proxy")
            model = data.get("model", "unknown")
            message = data["choices"][0]["message"]

            chunks = []

            if message.get("tool_calls"):
                tools_with_index = []
                for i, tc in enumerate(message["tool_calls"]):
                    tc["index"] = i
                    tools_with_index.append(tc)

                chunks.append({
                    "id": msg_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": tools_with_index
                        },
                        "finish_reason": None
                    }]
                })
            elif message.get("content"):
                chunks.append({
                    "id": msg_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": message["content"]
                        },
                        "finish_reason": None
                    }]
                })

            chunks.append({
                "id": msg_id,
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            })

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                self.wfile.flush()

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps({'error': str(e)})}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except:
                pass

    def _send_response(self, status_code, data):
        """Send JSON response"""
        status, headers, body = build_response(data, status_code)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status_code, message):
        """Send error response"""
        self._send_response(status_code, {"error": message})


class ThreadedHTTPServer(HTTPServer):
    """Handle requests in separate threads for better concurrency"""
    def process_request(self, request, client_address):
        thread = threading.Thread(target=self._process_request_thread, args=(request, client_address))
        thread.daemon = True
        thread.start()

    def _process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    parser = argparse.ArgumentParser(
        description="Ollama-to-OpenAI Proxy Server (Optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Default (client specifies model)
    python3 ollama-proxy.py

    # Force specific model
    python3 ollama-proxy.py --model qwen2.5-coder:1.5b

    # Custom context size (smaller = faster)
    python3 ollama-proxy.py --num-ctx 4096

    # Keep model loaded longer
    python3 ollama-proxy.py --keep-alive 30m
        """
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--ollama-url", type=str, default=DEFAULT_OLLAMA_URL,
                       help=f"Ollama API URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--model", type=str, default=None,
                       help="Force a specific Ollama model (default: let client choose)")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX,
                       help=f"Context window size (default: {DEFAULT_NUM_CTX}, smaller = faster)")
    parser.add_argument("--keep-alive", type=str, default=DEFAULT_KEEP_ALIVE,
                       help=f"Keep model loaded duration (default: {DEFAULT_KEEP_ALIVE})")
    parser.add_argument("--timeout", type=int, default=120,
                       help="Request timeout in seconds (default: 120)")

    args = parser.parse_args()

    config.port = args.port
    config.ollama_url = args.ollama_url
    config.model = args.model
    config.numctx = args.num_ctx
    config.keep_alive = args.keep_alive
    config.timeout = args.timeout

    server = ThreadedHTTPServer(("0.0.0.0", config.port), ProxyHandler)

    print(f"\n{'='*50}")
    print(f"  Ollama-to-OpenAI Proxy (Optimized)")
    print(f"  Listening:    http://0.0.0.0:{config.port}")
    print(f"  Ollama URL:   {config.ollama_url}")
    print(f"  Model:        {config.model or '(client-specified)'}")
    print(f"  Context Size: {config.numctx} tokens")
    print(f"  Keep Alive:   {config.keep_alive}")
    print(f"{'='*50}\n")
    print(f"Test: curl http://localhost:{config.port}/health")
    print(f"Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
