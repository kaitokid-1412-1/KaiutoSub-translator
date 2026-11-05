"""LLM client for OpenAI-compatible endpoints with SSE handling and retry."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import httpx

from subtrans.core.config import Config, ProviderConfig


class QuotaExhaustedError(Exception):
    """Raised when provider reports quota or credits exhausted."""
    pass


class LLMClientError(Exception):
    """General LLM client error."""
    pass


class FinishReasonLengthError(Exception):
    """Raised when completion was truncated due to max tokens."""
    pass


@dataclass
class LLMResponse:
    content: str
    finish_reason: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMClient:
    """Client for querying LLM providers with robust error handling, SSE recovery, and rate limiting."""

    def __init__(self, provider_cfg: ProviderConfig):
        self.cfg = provider_cfg
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self._request_timestamps: List[float] = []

    def _wait_for_rate_limit(self):
        """Enforce max_requests_per_minute rate limiting."""
        if not self.cfg.max_requests_per_minute or self.cfg.max_requests_per_minute <= 0:
            return

        now = time.time()
        # Keep timestamps from the last 60 seconds
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]

        if len(self._request_timestamps) >= self.cfg.max_requests_per_minute:
            oldest = self._request_timestamps[0]
            sleep_time = 60.0 - (now - oldest) + 0.1
            if sleep_time > 0:
                time.sleep(sleep_time)
                now = time.time()
                self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]

        self._request_timestamps.append(time.time())

    def _get_candidate_endpoints(self, base_url: str) -> List[str]:
        """Generate endpoint variants for 9Router/OpenAI-compatible gateways."""
        base = base_url.rstrip("/")
        candidates = []

        if base.endswith("/chat/completions"):
            candidates.append(base)
        else:
            candidates.append(f"{base}/chat/completions")
            if not base.endswith("/v1"):
                candidates.append(f"{base}/v1/chat/completions")
            if not base.endswith("/api/v1"):
                candidates.append(f"{base}/api/v1/chat/completions")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def _parse_sse_stream(self, text: str) -> Tuple[str, str]:
        """Parse SSE stream (data: lines) and aggregate choices[0].delta.content."""
        collected_chunks = []
        finish_reason = "stop"

        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue

            payload = line[5:].strip()
            if payload == "[DONE]":
                break

            try:
                data = json.loads(payload)
                choices = data.get("choices", [])
                if choices:
                    choice = choices[0]
                    delta = choice.get("delta", {})
                    # Content from delta, ignoring reasoning_content
                    content = delta.get("content")
                    if content:
                        collected_chunks.append(content)
                    if choice.get("finish_reason"):
                        finish_reason = choice.get("finish_reason")
            except Exception:
                continue

        return "".join(collected_chunks), finish_reason

    def _check_quota_exhausted(self, error_text: str):
        """Detect quota or resource exhaustion errors."""
        lower = error_text.lower()
        keywords = ["quota", "resource_exhausted", "insufficient_quota", "out of credits", "exceeded your current quota"]
        for kw in keywords:
            if kw in lower:
                raise QuotaExhaustedError(f"سهمیه API به پایان رسیده است: {error_text}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        json_mode: bool = True,
        max_attempts: int = 3,
        base_delay: float = 10.0,
    ) -> LLMResponse:
        """Execute chat completion with automatic retry, SSE parsing, and quota detection."""
        temp = temperature if temperature is not None else 0.3
        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": temp,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
        }
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        base_url = self.cfg.base_url.rstrip("/")
        is_local = "127.0.0.1" in base_url or "localhost" in base_url
        endpoints = self._get_candidate_endpoints(base_url)

        timeout = httpx.Timeout(self.cfg.request_timeout_seconds, connect=10.0)
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            self._wait_for_rate_limit()

            last_error: Optional[Exception] = None
            response_obj = None

            for endpoint in endpoints:
                try:
                    with httpx.Client(timeout=timeout, trust_env=not is_local) as client:
                        resp = client.post(endpoint, json=payload, headers=headers)

                    # Check for quota errors
                    if resp.status_code in (402, 429):
                        self._check_quota_exhausted(resp.text)

                    # If 404 or HTML, try next endpoint variant
                    if resp.status_code == 404 or ("text/html" in resp.headers.get("content-type", "").lower() and resp.status_code >= 400):
                        continue

                    # Rate limit 429 without explicit quota exhaustion
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait_sec = float(retry_after) if retry_after and retry_after.isdigit() else (base_delay * (2 ** attempt) + random.uniform(0.5, 2.0))
                        time.sleep(wait_sec)
                        break  # Retry outer loop

                    # Server errors 5xx
                    if resp.status_code >= 500:
                        wait_sec = base_delay * (2 ** attempt) + random.uniform(0.5, 2.0)
                        time.sleep(wait_sec)
                        break

                    # Client errors 4xx
                    if resp.status_code >= 400:
                        self._check_quota_exhausted(resp.text)
                        # If response_format caused an error (e.g. some gateways don't support json_object), retry without it
                        if json_mode and ("response_format" in resp.text.lower() or "schema" in resp.text.lower()):
                            payload.pop("response_format", None)
                            json_mode = False
                            continue
                        raise LLMClientError(f"HTTP {resp.status_code}: {resp.text}")

                    response_obj = resp
                    break  # Success on this endpoint

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_error = e
                    continue
                except QuotaExhaustedError:
                    raise
                except LLMClientError:
                    raise
                except Exception as e:
                    last_error = e
                    continue

            if response_obj is not None:
                text = response_obj.text.strip()

                # Handle SSE response if body starts with data: (SPEC section 4.8)
                if text.startswith("data:"):
                    content, finish_reason = self._parse_sse_stream(text)
                    p_tok, c_tok, t_tok = 0, 0, 0
                else:
                    try:
                        data = response_obj.json()
                    except Exception:
                        # Sometimes json is wrapped or prefixed
                        raise LLMClientError(f"Invalid JSON response from gateway: {text[:200]}")

                    choices = data.get("choices", [])
                    if not choices:
                        raise LLMClientError(f"Empty choices in response: {data}")

                    choice = choices[0]
                    finish_reason = choice.get("finish_reason", "stop")
                    msg = choice.get("message", {})
                    # Ignore reasoning_content per SPEC section 4.8
                    content = msg.get("content", "")

                    usage = data.get("usage", {})
                    p_tok = usage.get("prompt_tokens", 0)
                    c_tok = usage.get("completion_tokens", 0)
                    t_tok = usage.get("total_tokens", p_tok + c_tok)

                # Track metrics
                self.call_count += 1
                self.prompt_tokens += p_tok
                self.completion_tokens += c_tok
                self.total_tokens += t_tok

                # Check finish reason
                if finish_reason == "length":
                    raise FinishReasonLengthError("پاسخ مدل به دلیل محدودیت طول توکن نیمه‌کاره ماند (finish_reason=length).")

                return LLMResponse(
                    content=content,
                    finish_reason=finish_reason,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=t_tok,
                )

            # If all endpoints failed on this attempt, wait and retry
            if attempt < max_attempts - 1:
                wait_sec = base_delay * (2 ** attempt) + random.uniform(0.5, 2.0)
                time.sleep(wait_sec)

        raise LLMClientError(f"تلاش برای برقراری ارتباط پس از {max_attempts} بار ناموفق بود: {last_error}")

