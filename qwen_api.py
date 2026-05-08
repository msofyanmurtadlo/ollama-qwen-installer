from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import uvicorn
import json
import re

app = FastAPI(title="Qwen OpenAI-Compatible API")

OLLAMA_BASE_URL = "http://localhost:11434"

# Map Qwen Code model IDs to Ollama model names
MODEL_MAP = {
    "ollama-local": "qwen2.5-coder:14b",
    "ollama": "qwen2.5-coder:14b",
}

def resolve_model(model_name):
    return MODEL_MAP.get(model_name, model_name)

def transform_to_tool_call(response_json):
    try:
        choices = response_json.get("choices", [])
        if choices and len(choices) > 0:
            message = choices[0].get("message", {})
            content = message.get("content", "")

            if not content:
                return response_json

            # Try parsing entire content as JSON first
            try:
                data = json.loads(content.strip())
                if isinstance(data, dict) and "name" in data and "arguments" in data:
                    data_list = [data]
                elif isinstance(data, list):
                    data_list = data
                else:
                    data_list = []
            except json.JSONDecodeError:
                data_list = []

            # If direct parse failed, try regex
            if not data_list:
                # Try to find JSON blocks in content
                start = content.find('{')
                if start != -1:
                    # Find matching closing brace with balanced depth
                    depth = 0
                    end = start
                    for i, char in enumerate(content[start:], start):
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    
                    json_str = content[start:end]
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict) and "name" in data and "arguments" in data:
                            data_list = [data]
                        elif isinstance(data, list):
                            data_list = data
                        else:
                            data_list = []
                    except json.JSONDecodeError:
                        data_list = []

            tool_calls = []
            for i, call in enumerate(data_list):
                if isinstance(call, dict) and "name" in call:
                    arguments = call.get("arguments", call.get("parameters", {}))
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}_{i}",
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": arguments
                        }
                    })

            if tool_calls:
                message["tool_calls"] = tool_calls
                message["content"] = None
    except Exception as e:
        print(f"ERROR in transform_to_tool_call: {e}")

    return response_json

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    stream = body.get("stream", False)

    if stream:
        async def stream_generator():
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    # We override stream to False internally so we can transform the full response
                    internal_body = body.copy()
                    internal_body["model"] = resolve_model(internal_body["model"])
                    internal_body["stream"] = False
                    
                    body["model"] = resolve_model(body.get("model", "qwen2.5-coder:14b"))
                    response = await client.post(
                        f"{OLLAMA_BASE_URL}/v1/chat/completions",
                        json=internal_body,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    data = response.json()
                    data = transform_to_tool_call(data)
                    
                    msg_id = data.get("id", "chatcmpl-123")
                    model = data.get("model", "qwen2.5-coder:14b")
                    choices = data.get("choices", [])
                    if not choices or not choices[0].get("message"):
                        error_msg = data.get("error", "No choices in response")
                        raise ValueError(f"Ollama error: {error_msg}")
                    message = choices[0]["message"]
                    
                    if message.get("tool_calls"):
                        # Format tool calls specifically for OpenAI chunk format
                        # Tool calls need an 'index' in streaming mode
                        tools_with_index = []
                        for i, tc in enumerate(message["tool_calls"]):
                            tc["index"] = i
                            tools_with_index.append(tc)
                            
                        chunk = {
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
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    elif message.get("content"):
                        # Yield the whole content at once as a single chunk
                        chunk = {
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
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                        
                    # Stop chunk
                    end_chunk = {
                        "id": msg_id,
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(end_chunk)}\n\n"
                    yield "data: [DONE]\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/v1/chat/completions",
                    json=body,
                    headers={"Content-Type": "application/json"}
                )
                data = response.json()
                data = transform_to_tool_call(data)
                return data
            except httpx.RequestError as exc:
                raise HTTPException(status_code=500, detail=f"Error connecting to Ollama: {exc}")

@app.get("/v1/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_BASE_URL}/v1/models")
            return response.json()
        except:
            return {"object": "list", "data": []}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
