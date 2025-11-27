"""
Async API clients for LLM providers.
"""
import os
import re
import asyncio
from dataclasses import dataclass
from typing import Optional
import httpx


def sanitize_error(error: str) -> str:
    """Remove API keys and sensitive data from error messages."""
    # Pattern dla różnych formatów kluczy API
    patterns = [
        (r'key=[A-Za-z0-9_-]{20,}', 'key=***REDACTED***'),
        (r'sk-[A-Za-z0-9_-]{20,}', 'sk-***REDACTED***'),
        (r'sk-ant-[A-Za-z0-9_-]{20,}', 'sk-ant-***REDACTED***'),
        (r'AIzaSy[A-Za-z0-9_-]{30,}', '***REDACTED_GOOGLE_KEY***'),
        (r'Bearer [A-Za-z0-9_-]{20,}', 'Bearer ***REDACTED***'),
    ]
    result = error
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


@dataclass
class Response:
    provider: str
    model: str
    content: str
    error: Optional[str] = None
    
    @property
    def ok(self) -> bool:
        return self.error is None


class BaseProvider:
    name: str = "base"
    
    def __init__(self, config: dict):
        self.config = config
        self.api_key = self._resolve_key(config.get("api_key", ""))
        self.model = self._resolve_key(config.get("model", ""))
        self.base_url = self._resolve_key(config.get("base_url", ""))
        self.max_tokens = config.get("max_tokens", 4096)
        self.temperature = config.get("temperature", 0.7)
        self.timeout = config.get("timeout", 60)
    
    def _resolve_key(self, key: str) -> str:
        """Resolve ${ENV_VAR} or ${ENV_VAR:default} syntax."""
        if not isinstance(key, str):
            return str(key) if key else ""
        if key.startswith("${") and key.endswith("}"):
            inner = key[2:-1]
            if ":" in inner:
                env_var, default = inner.split(":", 1)
                return os.environ.get(env_var, default)
            else:
                return os.environ.get(inner, "")
        return key
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    name = "openai"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages if system else messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return Response(provider=self.name, model=self.model, content=content)
        except Exception as e:
            return Response(provider=self.name, model=self.model, content="", error=sanitize_error(str(e)))


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["content"][0]["text"]
                return Response(provider=self.name, model=self.model, content=content)
        except Exception as e:
            return Response(provider=self.name, model=self.model, content="", error=sanitize_error(str(e)))


class GoogleProvider(BaseProvider):
    name = "google"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        # Konwertuj format messages na format Gemini
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"[System instruction]: {system}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        
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
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["candidates"][0]["content"]["parts"][0]["text"]
                return Response(provider=self.name, model=self.model, content=content)
        except Exception as e:
            return Response(provider=self.name, model=self.model, content="", error=sanitize_error(str(e)))


class OllamaProvider(BaseProvider):
    name = "ollama"
    
    async def complete(self, messages: list[dict], system: str = "") -> Response:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages if system else messages,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                return Response(provider=self.name, model=self.model, content=content)
        except Exception as e:
            return Response(provider=self.name, model=self.model, content="", error=sanitize_error(str(e)))


PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider
}


def create_provider(name: str, config: dict) -> BaseProvider:
    """Factory function to create provider instances."""
    cls = PROVIDER_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}")
    return cls(config)


async def query_council(
    providers: list[BaseProvider],
    messages: list[dict],
    system: str = ""
) -> list[Response]:
    """Query all providers in parallel."""
    tasks = [p.complete(messages, system) for p in providers]
    return await asyncio.gather(*tasks)
