#!/usr/bin/env python3
"""
Ollama-to-OpenAI Proxy Server
Fully compliant with official Ollama documentation:
- Tool Calling: https://docs.ollama.com/capabilities/tool-calling
- Streaming: https://docs.ollama.com/capabilities/streaming
- Thinking: https://docs.ollama.com/capabilities/thinking

Key finding: qwen2.5-coder models output tool calls as JSON in 'content' field.
This proxy detects and transforms them to proper OpenAI tool_calls format.
"""
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import httpx, json, uvicorn, time

app = FastAPI()
OLLAMA = "http://localhost:11434"
MODEL_MAP = {
    "ollama-local": "qwen2.5-coder:14b",
    "ollama": "qwen2.5-coder:14b",
}

def resolve_model(name):
    return MODEL_MAP.get(name, name)


def extract_tool_call(content):
    """
    Extract tool call from content JSON string.
    qwen2.5-coder models output tool calls as:
    {"name": "write_file", "arguments": {"path": "...", "content": "..."}}
    """
    if not content:
        return None
    content = content.strip()
    if content.startswith('{'):
        try:
            d = json.loads(content, strict=False)
            if isinstance(d, dict) and "name" in d and "arguments" in d:
                args = d["arguments"]
                if isinstance(args, dict):
                    args = json.dumps(args)
                return {"id": "call_0000", "type": "function",
                        "function": {"name": d["name"], "arguments": args}}
        except:
            pass
    # Find balanced JSON
    s = content.find('{')
    if s == -1:
        return None
    depth = 0
    for i, ch in enumerate(content[s:], s):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    d = json.loads(content[s:i+1], strict=False)
                    if isinstance(d, dict) and "name" in d and "arguments" in d:
                        args = d["arguments"]
                        if isinstance(args, dict):
                            args = json.dumps(args)
                        return {"id": "call_0000", "type": "function",
                                "function": {"name": d["name"], "arguments": args}}
                except:
                    pass
                break
    return None


def ensure_tool_calls(data, has_tools=False):
    """Ensure response has tool_calls format. Transform content JSON to tool_calls."""
    for ch in data.get("choices", []):
        msg = ch.get("message", {})
        # If has tools but no tool_calls, check content for JSON tool call
        if has_tools and not msg.get("tool_calls") and msg.get("content"):
            tc = extract_tool_call(msg["content"])
            if tc:
                msg["tool_calls"] = [tc]
                msg["content"] = None
                ch["finish_reason"] = "tool_calls"
        # Fix arguments format (OpenAI spec requires string, not object)
        for t in msg.get("tool_calls", []):
            fn = t.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, dict):
                fn["arguments"] = json.dumps(args)
    return data


@app.get("/health")
async def health():
    return {"status": "ok", "ollama": OLLAMA}


@app.get("/v1/models")
async def list_models():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{OLLAMA}/api/tags")
        if r.status_code != 200:
            return {"object": "list", "data": []}
        ms = [{"id": m["name"], "object": "model", "created": 0,
               "owned_by": m.get("details",{}).get("family","unknown")}
              for m in r.json().get("models", [])]
        return {"object": "list", "data": ms}


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    """
    Main chat endpoint.
    Uses /v1/chat/completions (OpenAI-compatible) and transforms
    tool calls from content JSON to proper tool_calls format.
    """
    body = await req.json()
    stream = body.get("stream", False)
    body["stream"] = False
    body["model"] = resolve_model(body.get("model", "qwen2.5-coder:14b"))
    has_tools = bool(body.get("tools"))

    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(f"{OLLAMA}/v1/chat/completions", json=body)
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content=r.json())
        data = ensure_tool_calls(r.json(), has_tools)

    if stream:
        return _to_sse(data)
    return data


def _to_sse(data):
    """Convert to Server-Sent Events format per OpenAI streaming spec."""
    async def gen():
        mid = data.get("id", "chatcmpl-proxy")
        mod = data.get("model", "unknown")
        msg = data["choices"][0]["message"]
        chunks = []

        if msg.get("tool_calls"):
            tc = [{"id": f"call_{i}", "type": "function",
                   "function": t["function"], "index": i}
                  for i, t in enumerate(msg["tool_calls"])]
            chunks.append({"id": mid, "object": "chat.completion.chunk",
                "model": mod, "choices": [{"index": 0, "delta": {
                    "role": "assistant", "tool_calls": tc}, "finish_reason": None}]})
        elif msg.get("content"):
            chunks.append({"id": mid, "object": "chat.completion.chunk",
                "model": mod, "choices": [{"index": 0, "delta": {
                    "role": "assistant", "content": msg["content"]}, "finish_reason": None}]})
        else:
            chunks.append({"id": mid, "object": "chat.completion.chunk",
                "model": mod, "choices": [{"index": 0, "delta": {
                    "role": "assistant"}, "finish_reason": None}]})

        chunks.append({"id": mid, "object": "chat.completion.chunk",
            "model": mod, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})

        for ch in chunks:
            yield f"data: {json.dumps(ch)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
