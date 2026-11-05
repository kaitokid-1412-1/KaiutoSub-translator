"""OpenAI-compatible mock LLM server for automated testing.

Supports modes specified in SPEC section 10:
- normal: standard valid response
- sse_only: streaming SSE format response
- drops_id: drops an id from the output
- merges_lines: merges two lines into one
- rate_limit_429: returns 429 status n times before succeeding
- finish_reason_length: returns finish_reason="length"
- html_error: returns HTML on first request
- garbled_json: returns invalid/malformed JSON
- mangles_tokens: corrupts or strips tag tokens
- logs every incoming request for verification
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
import uvicorn


@dataclass
class MockLLMConfig:
    mode: str = "normal"  # normal, sse_only, drops_id, merges_lines, 429_n, length, html, garbled, mangles_tokens
    rate_limit_count: int = 2
    rate_limit_counter: int = 0
    html_counter: int = 0
    logged_requests: List[Dict[str, Any]] = field(default_factory=list)


def create_mock_llm_app(config: Optional[MockLLMConfig] = None) -> FastAPI:
    if config is None:
        config = MockLLMConfig()

    app = FastAPI(title="Mock LLM Server")
    app.state.config = config

    @app.get("/models")
    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                {"id": "gpt-4o-mini", "object": "model", "owned_by": "mock"},
                {"id": "deepseek-chat", "object": "model", "owned_by": "mock"},
                {"id": "gemini-2.5-flash", "object": "model", "owned_by": "mock"},
            ],
        }

    @app.post("/chat/completions")
    @app.post("/v1/chat/completions")
    @app.post("/api/v1/chat/completions")
    async def chat_completions(request: Request):
        cfg: MockLLMConfig = app.state.config
        body = await request.json()
        cfg.logged_requests.append({
            "path": request.url.path,
            "headers": dict(request.headers),
            "body": body,
        })

        # Mode: 429 rate limit n times
        if cfg.mode == "429_n":
            if cfg.rate_limit_counter < cfg.rate_limit_count:
                cfg.rate_limit_counter += 1
                raise HTTPException(
                    status_code=429,
                    detail={"error": {"message": "Rate limit exceeded (mock 429)", "type": "requests", "code": "rate_limit_exceeded"}},
                    headers={"Retry-After": "1"},
                )

        # Mode: HTML error on first path
        if cfg.mode == "html":
            if cfg.html_counter == 0:
                cfg.html_counter += 1
                return HTMLResponse(content="<html><body>Error 404 / Gateway not found</body></html>", status_code=404)

        messages = body.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        # Extract source lines from payload if provided
        # Standard expected payload structure in system/user message:
        # lines: [{"id": 1, "text": "Hello"}]
        try:
            # Look for lines list in JSON if sent directly
            payload_data = json.loads(last_msg) if isinstance(last_msg, str) and last_msg.strip().startswith("{") else {}
            input_lines = payload_data.get("lines", [])
        except Exception:
            input_lines = []

        translated_lines = []
        for line in input_lines:
            lid = line.get("id", 1)
            text = line.get("text", "")
            # Simple mock translation
            translated_lines.append({
                "id": lid,
                "translated_text": f"ترجمه: {text}",
            })

        if not translated_lines:
            # Fallback default lines if prompt format was different
            translated_lines = [{"id": 1, "translated_text": "ترجمه تست"}]

        # Mode manipulations
        finish_reason = "stop"
        if cfg.mode == "length":
            finish_reason = "length"
            translated_lines = translated_lines[: max(1, len(translated_lines) // 2)]
        elif cfg.mode == "drops_id" and len(translated_lines) > 1:
            translated_lines = translated_lines[1:]
        elif cfg.mode == "merges_lines" and len(translated_lines) > 1:
            translated_lines[0]["translated_text"] += " " + translated_lines[1]["translated_text"]
            translated_lines.pop(1)
        elif cfg.mode == "mangles_tokens":
            for line in translated_lines:
                # Remove or mangle token format [[T...]]
                line["translated_text"] = line["translated_text"].replace("[[", "").replace("]]", "")

        content_obj = {"lines": translated_lines}
        content_str = json.dumps(content_obj, ensure_ascii=False)

        if cfg.mode == "garbled_json":
            content_str = "{" + content_str[10:]  # Break json syntax

        # Mode: sse_only
        if cfg.mode == "sse_only" or body.get("stream", False):
            def sse_generator():
                chunk_data = {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": content_str},
                        "finish_reason": finish_reason,
                    }],
                }
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse_generator(), media_type="text/event-stream")

        return {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content_str,
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }

    return app
