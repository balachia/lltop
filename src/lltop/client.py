"""llama-swap HTTP client + typed responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import urlparse

import httpx

# Distinct UA so lltop's own polling traffic is identifiable in llama-swap's
# request log (and thus filterable from the log pane).
USER_AGENT = "lltop"


@dataclass(frozen=True)
class Model:
    id: str
    created: int
    owned_by: str

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Model:
        return cls(id=d["id"], created=d["created"], owned_by=d["owned_by"])


@dataclass(frozen=True)
class RunningModel:
    model: str
    state: str
    proxy: str
    ttl: int
    cmd: str
    port: int

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> RunningModel:
        proxy = d["proxy"]
        port = urlparse(proxy).port
        if port is None:
            raise ValueError(f"could not parse port from proxy={proxy!r}")
        return cls(
            model=d["model"],
            state=d["state"],
            proxy=proxy,
            ttl=d["ttl"],
            cmd=d["cmd"],
            port=port,
        )


@dataclass(frozen=True)
class ActivityLogEntry:
    id: int
    timestamp: str
    model: str
    req_path: str
    status_code: int
    input_tokens: int
    output_tokens: int
    cache_tokens: int
    prompt_per_second: float
    tokens_per_second: float
    duration_ms: int

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> ActivityLogEntry:
        toks = d.get("tokens") or {}
        return cls(
            id=d["id"],
            timestamp=d["timestamp"],
            model=d["model"],
            req_path=d["req_path"],
            status_code=d["resp_status_code"],
            input_tokens=toks.get("input_tokens", 0),
            output_tokens=toks.get("output_tokens", 0),
            cache_tokens=toks.get("cache_tokens", 0),
            prompt_per_second=toks.get("prompt_per_second", 0.0),
            tokens_per_second=toks.get("tokens_per_second", 0.0),
            duration_ms=d["duration_ms"],
        )


@dataclass(frozen=True)
class Slot:
    id: int
    n_ctx: int
    is_processing: bool
    speculative: bool
    id_task: int | None = None

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Slot:
        return cls(
            id=d["id"],
            n_ctx=d["n_ctx"],
            is_processing=d["is_processing"],
            speculative=d.get("speculative", False),
            id_task=d.get("id_task"),
        )


class LlamaSwapClient:
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[Model]:
        r = await self._client.get("/v1/models")
        r.raise_for_status()
        return [Model.from_json(d) for d in r.json()["data"]]

    async def running_models(self) -> list[RunningModel]:
        r = await self._client.get("/running")
        r.raise_for_status()
        return [RunningModel.from_json(d) for d in r.json()["running"]]

    async def metrics(self) -> list[ActivityLogEntry]:
        r = await self._client.get("/api/metrics")
        r.raise_for_status()
        return [ActivityLogEntry.from_json(d) for d in r.json()]

    async def slots(self, model_id: str) -> list[Slot]:
        r = await self._client.get(f"/upstream/{model_id}/slots")
        r.raise_for_status()
        return [Slot.from_json(d) for d in r.json()]

    async def unload(self, model_id: str) -> None:
        """Unload one model via POST /api/models/unload/<id>.

        Note: the legacy GET /unload?model=<id> silently ignores the param and
        unloads everything; the per-model route is POST-only (what the web UI uses).
        """
        r = await self._client.post(f"/api/models/unload/{model_id}")
        r.raise_for_status()

    async def unload_all(self) -> None:
        r = await self._client.post("/api/models/unload")
        r.raise_for_status()

    async def load(self, model_id: str) -> None:
        """Warm a model by hitting its upstream health endpoint, which forces
        llama-swap to spawn it. Cold loads can take minutes, so the read timeout
        is disabled for this request only."""
        r = await self._client.get(
            f"/upstream/{model_id}/health",
            timeout=httpx.Timeout(5.0, read=None),
        )
        r.raise_for_status()
