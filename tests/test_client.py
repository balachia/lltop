"""TDD: llama-swap HTTP client."""

from __future__ import annotations

import httpx
import pytest
import respx

from lltop.client import (
    ActivityLogEntry,
    LlamaSwapClient,
    Model,
    RunningModel,
    Slot,
)

BASE = "http://test:1135"


# ---- list_models ----------------------------------------------------------


@respx.mock
async def test_list_models_parses_eight_configured(fx_v1_models):
    respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json=fx_v1_models))
    async with LlamaSwapClient(BASE) as client:
        models = await client.list_models()
    assert len(models) == 8
    ids = [m.id for m in models]
    assert "gemma4-31b" in ids
    assert "gemma4-26b-a4b" in ids
    assert "mistral-medium-3.5" in ids


@respx.mock
async def test_list_models_returns_model_objects(fx_v1_models):
    respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json=fx_v1_models))
    async with LlamaSwapClient(BASE) as client:
        models = await client.list_models()
    assert all(isinstance(m, Model) for m in models)
    assert all(m.owned_by == "llama-swap" for m in models)


# ---- running_models -------------------------------------------------------


@respx.mock
async def test_running_models_empty_when_idle(fx_running_idle):
    respx.get(f"{BASE}/running").mock(return_value=httpx.Response(200, json=fx_running_idle))
    async with LlamaSwapClient(BASE) as client:
        running = await client.running_models()
    assert running == []


@respx.mock
async def test_running_models_one_loaded(fx_running_one_loaded):
    respx.get(f"{BASE}/running").mock(
        return_value=httpx.Response(200, json=fx_running_one_loaded)
    )
    async with LlamaSwapClient(BASE) as client:
        running = await client.running_models()
    assert len(running) == 1
    rm = running[0]
    assert isinstance(rm, RunningModel)
    assert rm.model == "gemma4-e4b"
    assert rm.state == "ready"
    assert rm.proxy == "http://localhost:5802"
    assert rm.ttl == 600


@respx.mock
async def test_running_model_extracts_port_from_cmd(fx_running_one_loaded):
    """The port in cmd should be parsed for PID-to-model mapping later."""
    respx.get(f"{BASE}/running").mock(
        return_value=httpx.Response(200, json=fx_running_one_loaded)
    )
    async with LlamaSwapClient(BASE) as client:
        running = await client.running_models()
    assert running[0].port == 5802


# ---- metrics --------------------------------------------------------------


@respx.mock
async def test_metrics_empty_returns_empty_list(fx_api_metrics_empty):
    respx.get(f"{BASE}/api/metrics").mock(
        return_value=httpx.Response(200, json=fx_api_metrics_empty)
    )
    async with LlamaSwapClient(BASE) as client:
        m = await client.metrics()
    assert m == []


@respx.mock
async def test_metrics_populated_parses_entries(fx_api_metrics_populated):
    respx.get(f"{BASE}/api/metrics").mock(
        return_value=httpx.Response(200, json=fx_api_metrics_populated)
    )
    async with LlamaSwapClient(BASE) as client:
        m = await client.metrics()
    assert len(m) == 27
    first = m[0]
    assert isinstance(first, ActivityLogEntry)
    assert first.model == "gemma4-26b-a4b"
    assert first.input_tokens == 556
    assert first.output_tokens == 271
    assert first.duration_ms == 13616
    assert first.status_code == 200


@respx.mock
async def test_metrics_tokens_per_second_parsed(fx_api_metrics_populated):
    """Verify decode speed signal is preserved."""
    respx.get(f"{BASE}/api/metrics").mock(
        return_value=httpx.Response(200, json=fx_api_metrics_populated)
    )
    async with LlamaSwapClient(BASE) as client:
        m = await client.metrics()
    assert m[0].tokens_per_second == pytest.approx(91.305, rel=1e-3)


# ---- slots ----------------------------------------------------------------


@respx.mock
async def test_slots_idle_all_not_processing(fx_slots_idle):
    respx.get(f"{BASE}/upstream/gemma4-e4b/slots").mock(
        return_value=httpx.Response(200, json=fx_slots_idle)
    )
    async with LlamaSwapClient(BASE) as client:
        slots = await client.slots("gemma4-e4b")
    assert len(slots) == 4
    assert all(isinstance(s, Slot) for s in slots)
    assert not any(s.is_processing for s in slots)


@respx.mock
async def test_slots_one_processing_detected(fx_slots_one_processing):
    respx.get(f"{BASE}/upstream/gemma4-31b/slots").mock(
        return_value=httpx.Response(200, json=fx_slots_one_processing)
    )
    async with LlamaSwapClient(BASE) as client:
        slots = await client.slots("gemma4-31b")
    active = [s for s in slots if s.is_processing]
    assert len(active) == 1
    assert active[0].id == 1
    assert active[0].n_ctx == 262144


# ---- error handling -------------------------------------------------------


@respx.mock
async def test_list_models_raises_on_5xx():
    respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(500))
    async with LlamaSwapClient(BASE) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.list_models()


@respx.mock
async def test_client_uses_short_timeout_by_default():
    """For statusline use, hung llama-swap shouldn't block forever."""
    async with LlamaSwapClient(BASE) as client:
        assert client._client.timeout.connect <= 2.0


@respx.mock
async def test_client_sends_lltop_user_agent():
    """Own requests must be tagged so the log pane can filter them out."""
    route = respx.get(f"{BASE}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [], "object": "list"})
    )
    async with LlamaSwapClient(BASE) as client:
        await client.list_models()
    assert "lltop" in route.calls.last.request.headers["user-agent"]


# ---- unload ---------------------------------------------------------------


@respx.mock
async def test_unload_targets_specific_model():
    # per-model unload is POST /api/models/unload/<id> (GET /unload?model ignores param)
    route = respx.post(f"{BASE}/api/models/unload/gemma4-31b").mock(
        return_value=httpx.Response(200, text="OK")
    )
    async with LlamaSwapClient(BASE) as client:
        await client.unload("gemma4-31b")
    assert route.called


@respx.mock
async def test_unload_all_hits_bare_route():
    route = respx.post(f"{BASE}/api/models/unload").mock(
        return_value=httpx.Response(200, text="OK")
    )
    async with LlamaSwapClient(BASE) as client:
        await client.unload_all()
    assert route.called


@respx.mock
async def test_unload_raises_on_error():
    respx.post(f"{BASE}/api/models/unload/m1").mock(return_value=httpx.Response(500))
    async with LlamaSwapClient(BASE) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.unload("m1")


# ---- load -----------------------------------------------------------------


@respx.mock
async def test_load_warms_via_upstream_health():
    route = respx.get(f"{BASE}/upstream/gemma4-31b/health").mock(
        return_value=httpx.Response(200, text="OK")
    )
    async with LlamaSwapClient(BASE) as client:
        await client.load("gemma4-31b")
    assert route.called


@respx.mock
async def test_load_uses_long_timeout():
    """Cold loads can take many seconds; load() must not use the 2s default."""
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, text="OK")

    respx.get(f"{BASE}/upstream/m1/health").mock(side_effect=_handler)
    async with LlamaSwapClient(BASE) as client:
        await client.load("m1")
    # connect timeout should be well above the 2s status-line default
    assert captured["timeout"]["read"] is None or captured["timeout"]["read"] > 10
