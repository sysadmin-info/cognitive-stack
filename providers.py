"""
Async API clients for LLM providers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, ClassVar

import httpx

__all__ = [
    "Response",
    "BaseProvider", 
    "OpenAIProvider",
    "AnthropicProvider", 
    "GoogleProvider",
    "OllamaProvider",
    "create_provider",
    "query_council",
    "sanitize_error",
]

logger = logging.getLogger(__name__)


# Patterns for sanitizing API keys in error messages
_SANITIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'key=[A-Za-z0-9_-]{15,}'), 'key=***REDACTED***'),
    (re.compile(r'sk-proj-[A-Za-z0-9_-]{20,}'), 'sk-proj-***REDACTED***'),
    (re.compile(r'sk-[A-Za-z0-9_-]{20,}'), 'sk-***REDACTED***'),
    (re.compile(r'sk-ant-api[A-Za-z0-9_-]{20,}'), 'sk-ant-***REDACTED***'),
    (re.compile(r'AIzaSy[A-Za-z0-9_-]{30,}'), '***REDACTED_GOOGLE_KEY***'),
    (re.compile(r'Bearer [A-Za-z0-9_-]{20,}'), 'Bearer ***REDACTED***'),
    (re.compile(r'x-api-key: [A-Za-z0-9_-]{20,}'), 'x-api-key: ***REDACTED***'),
]


def sanitize_error(error: str) -> str:
    """Remove API keys and sensitive data from error messages."""
    result = str(error)
    for pattern, replacement in _SANITIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


@dataclass
class Response:
    """Response from an LLM provider."""
    provider: str
    model: str
    content: str
    error: Optional[str] = None
    usage: Optional[dict] = field(default=None, repr=False)
    
    @property
    def ok(self) -> bool:
        """Check if response was successful."""
        return self.error is None


def _safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dict keys."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is default:
            return default
    return data


class BaseProvider:
    """Base class for LLM providers."""
    
    name: ClassVar[str] = "base"
    
    def __init__(self, config: dict):
        self.config = config
        self.api_key = self._resolve_env(config.get("api_key", ""))
        self.model = self._resolve_env(config.get("model", ""))
        self.base_url = self._resolve_env(config.get("base_url", ""))
        self.max_tokens = int(config.get("max_tokens", 4096))
        self.temperature = float(config.get("temperature", 0.7))
        self.timeout = min(int(config.get("timeout", 60)), 300)  # Max 5 min
        self.max_retries = int(config.get("max_retries", 2))
        self._client: Optional[httpx.AsyncClient] = None
    
    @staticmethod
    def _resolve_env(value: str) -> str:
        """Resolve ${ENV_VAR} or ${ENV_VAR:default} syntax."""
        if not isinstance(value, str):
            return str(value) if value else ""
        if value.startswith("${") and value.endswith("}"):
            inner = value[2:-1]
            if ":" in inner:
                env_var, default = inner.split(":", 1)
                return os.environ.get(env_var, default)
            return os.environ.get(inner, "")
        return value
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection reuse."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=10)
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        """Send completion request. Must be implemented by subclasses."""
        raise NotImplementedError
    
    async def _request_with_retry(
        self, 
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        client = await self._get_client()
        last_error: Optional[Exception] = None
        
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                # Don't retry 4xx errors (except 429)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                last_error = e
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
            
            if attempt < self.max_retries:
                wait_time = (2 ** attempt) + 0.5  # Exponential backoff
                logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {self.name} after {wait_time}s")
                await asyncio.sleep(wait_time)
        
        raise last_error or RuntimeError("Request failed")


class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""
    
    name: ClassVar[str] = "openai"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        all_messages = messages.copy()
        if system:
            all_messages.insert(0, {"role": "system", "content": system})
        
        payload = {
            "model": self.model,
            "messages": all_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            resp = await self._request_with_retry(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            data = resp.json()
            
            content = _safe_get(data, "choices", 0, "message", "content", default="")
            usage = _safe_get(data, "usage")
            
            if not content:
                return Response(
                    provider=self.name, 
                    model=self.model, 
                    content="",
                    error="Empty response from API"
                )
            
            return Response(
                provider=self.name, 
                model=self.model, 
                content=content,
                usage=usage
            )
        except Exception as e:
            logger.error(f"OpenAI error: {sanitize_error(str(e))}")
            return Response(
                provider=self.name, 
                model=self.model, 
                content="", 
                error=sanitize_error(str(e))
            )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""
    
    name: ClassVar[str] = "anthropic"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages
        }
        if system:
            payload["system"] = system
        
        try:
            resp = await self._request_with_retry(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload
            )
            data = resp.json()
            
            content = _safe_get(data, "content", 0, "text", default="")
            usage = _safe_get(data, "usage")
            
            if not content:
                return Response(
                    provider=self.name,
                    model=self.model,
                    content="",
                    error="Empty response from API"
                )
            
            return Response(
                provider=self.name,
                model=self.model,
                content=content,
                usage=usage
            )
        except Exception as e:
            logger.error(f"Anthropic error: {sanitize_error(str(e))}")
            return Response(
                provider=self.name,
                model=self.model,
                content="",
                error=sanitize_error(str(e))
            )


class GoogleProvider(BaseProvider):
    """Google Gemini API provider."""
    
    name: ClassVar[str] = "google"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        contents = []
        
        # Gemini supports systemInstruction natively now
        system_instruction = None
        if system:
            system_instruction = {"parts": [{"text": system}]}
        
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": self.temperature
            }
        }
        
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        
        try:
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            resp = await self._request_with_retry("POST", url, json=payload)
            data = resp.json()
            
            content = _safe_get(
                data, "candidates", 0, "content", "parts", 0, "text", 
                default=""
            )
            usage = _safe_get(data, "usageMetadata")
            
            if not content:
                # Check for safety blocks
                block_reason = _safe_get(data, "candidates", 0, "finishReason")
                if block_reason and block_reason != "STOP":
                    return Response(
                        provider=self.name,
                        model=self.model,
                        content="",
                        error=f"Response blocked: {block_reason}"
                    )
                return Response(
                    provider=self.name,
                    model=self.model,
                    content="",
                    error="Empty response from API"
                )
            
            return Response(
                provider=self.name,
                model=self.model,
                content=content,
                usage=usage
            )
        except Exception as e:
            logger.error(f"Google error: {sanitize_error(str(e))}")
            return Response(
                provider=self.name,
                model=self.model,
                content="",
                error=sanitize_error(str(e))
            )


class OllamaProvider(BaseProvider):
    """Ollama local API provider."""
    
    name: ClassVar[str] = "ollama"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        all_messages = messages.copy()
        if system:
            all_messages.insert(0, {"role": "system", "content": system})
        
        payload = {
            "model": self.model,
            "messages": all_messages,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature
            }
        }
        
        try:
            resp = await self._request_with_retry(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload
            )
            data = resp.json()
            
            content = _safe_get(data, "message", "content", default="")
            
            if not content:
                return Response(
                    provider=self.name,
                    model=self.model,
                    content="",
                    error="Empty response from API"
                )
            
            return Response(
                provider=self.name,
                model=self.model,
                content=content
            )
        except Exception as e:
            logger.error(f"Ollama error: {sanitize_error(str(e))}")
            return Response(
                provider=self.name,
                model=self.model,
                content="",
                error=sanitize_error(str(e))
            )


PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider
}


def create_provider(name: str, config: dict) -> BaseProvider:
    """Factory function to create provider instances."""
    cls = PROVIDER_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDER_CLASSES.keys())}")
    return cls(config)


async def query_council(
    providers: list[BaseProvider],
    messages: list[dict],
    system: str = ""
) -> list[Response]:
    """Query all providers in parallel."""
    if not providers:
        return []
    
    tasks = [p.complete(messages, system) for p in providers]
    return await asyncio.gather(*tasks, return_exceptions=False)


async def close_all_providers(providers: list[BaseProvider]) -> None:
    """Close all provider HTTP clients."""
    await asyncio.gather(*[p.close() for p in providers], return_exceptions=True)
