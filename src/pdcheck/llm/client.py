"""LLM clients for the agent layer.

The default backend is Ollama running locally (no account, no API key, nothing
leaves the machine). Every call asks for JSON that matches a schema, runs at
temperature 0, and is cached on disk so that re-running the eval is free and
gives identical results.

Configuration (environment variables)
-------------------------------------
PDCHECK_LLM_MODEL    Ollama model tag            default: qwen3:4b
PDCHECK_OLLAMA_URL   Ollama server URL           default: http://localhost:11434
PDCHECK_LLM_OFFLINE  "1" = only read the cache, never call the model
PDCHECK_LLM_TIMEOUT  seconds per request          default: 300
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "llm_cache"

# Bump when prompts/schemas change in a way that should invalidate old cache entries.
CACHE_VERSION = 1


class LLMError(RuntimeError):
    """The model answered, but not with usable JSON."""


class LLMUnavailable(RuntimeError):
    """The model could not be reached (server down, model not pulled, offline cache miss)."""


@dataclass
class LLMResponse:
    data: dict[str, Any]
    model: str
    cached: bool
    latency_ms: int


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

class _DiskCache:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    @staticmethod
    def key(model: str, system: str, user: str, schema: dict[str, Any]) -> str:
        blob = json.dumps(
            {"v": CACHE_VERSION, "model": model, "system": system, "user": user, "schema": schema},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["response"]

    def put(self, key: str, model: str, user: str, response: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{key}.json"
        record = {"model": model, "user": user, "response": response}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

class OllamaClient:
    """Calls a local Ollama server's /api/chat with a JSON schema as `format`."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        offline: bool | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = model or os.environ.get("PDCHECK_LLM_MODEL", "qwen3:4b")
        self.base_url = (base_url or os.environ.get("PDCHECK_OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.cache = _DiskCache(cache_dir) if cache_dir is not None else None
        self.offline = offline if offline is not None else os.environ.get("PDCHECK_LLM_OFFLINE") == "1"
        self.timeout = timeout or float(os.environ.get("PDCHECK_LLM_TIMEOUT", "300"))
        self._send_think = True  # dropped automatically if the model rejects it

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        key = _DiskCache.key(self.model, system, user, schema)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return LLMResponse(data=hit, model=self.model, cached=True, latency_ms=0)
        if self.offline:
            raise LLMUnavailable(
                f"Offline mode and no cached answer for this prompt (model {self.model}). "
                "Unset PDCHECK_LLM_OFFLINE and start Ollama to generate it."
            )

        start = time.perf_counter()
        content = self._chat(system, user, schema)
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {content[:200]!r}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"Model returned JSON that is not an object: {content[:200]!r}")

        if self.cache is not None:
            self.cache.put(key, self.model, user, data)
        return LLMResponse(data=data, model=self.model, cached=False, latency_ms=latency_ms)

    # -- HTTP ---------------------------------------------------------------

    def _chat(self, system: str, user: str, schema: dict[str, Any]) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "seed": 42},
        }
        if self._send_think:
            body["think"] = False  # qwen3 etc. otherwise spend minutes "thinking"
        try:
            resp = self._post("/api/chat", body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 400 and "think" in detail.lower() and self._send_think:
                self._send_think = False
                return self._chat(system, user, schema)
            if exc.code == 404:
                raise LLMUnavailable(
                    f"Ollama does not have model '{self.model}'. Run:  ollama pull {self.model}"
                ) from exc
            raise LLMUnavailable(f"Ollama returned HTTP {exc.code}: {detail[:300]}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise LLMUnavailable(
                f"Cannot reach Ollama at {self.base_url}. Is it running? "
                "Open the Ollama app (or run `ollama serve`), then try again."
            ) from exc
        try:
            return resp["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Ollama response: {str(resp)[:300]}") from exc

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Fake client for tests
# ---------------------------------------------------------------------------

class FakeClient:
    """Returns canned answers. `responder(system, user, schema) -> dict`."""

    def __init__(self, responder: Callable[[str, str, dict[str, Any]], dict[str, Any]], model: str = "fake") -> None:
        self.responder = responder
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        self.calls.append((system, user))
        return LLMResponse(data=self.responder(system, user, schema), model=self.model, cached=False, latency_ms=0)
