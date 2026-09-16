"""Openmart catalog, connection, capacity, routing, and shared-key safety boundaries."""
import json

import httpx
import pytest

from treg.application.call import service
from treg.config import get_settings
from treg.domain.catalog import store
from treg.domain.capacity import collectors
from treg.domain.capacity.policy import default_policy
from treg import oauth_providers as P
from test_marketplace_call import _balance, _entries, platform_on


@pytest.fixture
def openmart_on(monkeypatch, platform_on):
    monkeypatch.setenv("TREG_PLATFORM_KEY_OPENMART", "PLATFORM-OPENMART")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "openmart")
    get_settings.cache_clear()


def test_surface_is_complete_and_entirely_byok():
    cat = store.load()
    rows = cat.for_provider("openmart")
    assert len(rows) == 17
    assert len({(e["method"], e["path"]) for e in rows}) == 17
    assert not {e["id"] for e in rows if cat.platform_eligible(e)}
    assert all(e.get("platform_blocked") for e in rows)
    assert all(e.get("verified") and e.get("example_file") for e in rows)
    assert cat.credit_rates["openmart"] == .0298


def test_pricing_and_lifecycle_boundaries_stay_visible():
    cat = store.load()
    assert cat.by_id["openmart.people.find.batch"]["cost"]["value"] == 11
    assert cat.by_id["openmart.technologies.find.batch"]["cost"]["value"] == 2
    company_email = cat.by_id["openmart.companies.email.find.batch"]
    assert company_email["cost"]["confidence"] == "unknown"
    assert "0.3" in company_email["cost"]["note"] and "1" in company_email["cost"]["note"]
    fast = cat.by_id["openmart.businesses.search.ids"]
    assert fast["cost"]["value"] is None and fast["cost"]["confidence"] == "unknown"
    assert all(cat.by_id[key]["scope"] == "own_account" for key in (
        "openmart.tasks.batch.status", "openmart.tasks.batch.ids", "openmart.tasks.get",
        "openmart.deny-rules.create", "openmart.deny-rules.check",
        "openmart.deny-rules.delete", "openmart.account.balance",
    ))
    assert cat.by_id["openmart.deny-rules.delete"]["cache"] == "forbidden"


def test_connection_binding_and_config_contract(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_OPENMART", "platform")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "openmart")
    get_settings.cache_clear()
    p = P.get("openmart")
    assert p.base_url == "https://api.openmart.ai"
    assert p.probe_path == "/api/v2/credit-balance" and p.probe_method == "GET"
    binding = P.platform_bindings(p)[0]
    assert binding == {
        "location": "header", "name": "Authorization", "format": "Bearer {secret}",
        "platform_setting": "platform_key_openmart", "injector": "env",
    }
    assert get_settings().platform_key_for("openmart") == "platform"


async def test_connection_probe_rejects_bad_key_and_saves_good_key(clients, monkeypatch):
    from treg.api import app

    def probe(request):
        assert request.method == "GET" and request.url.path.endswith("/api/v2/credit-balance")
        if request.headers["authorization"] == "Bearer bogus":
            return httpx.Response(401, json={"detail": "Invalid API Key"})
        return httpx.Response(200, json={"balance": 4800})

    async with httpx.AsyncClient(transport=httpx.MockTransport(probe)) as upstream:
        monkeypatch.setattr(app.state, "http", upstream)
        bad = await clients.post("/connections/token", json={"provider": "openmart", "token": "bogus"})
        assert bad.status_code == 422
        good = await clients.post("/connections/token", json={"provider": "openmart", "token": "good"})
        assert good.status_code == 200, good.text


async def test_platform_key_is_blocked_before_relay_or_money(clients, openmart_on, monkeypatch):
    before = await _balance(clients)

    async def forbidden(*args, **kwargs):
        raise AssertionError("platform guard must precede relay")

    monkeypatch.setattr(service, "relay", forbidden)
    response = await clients.post("/call/openmart.businesses.search", json={
        "query": {"search_term": "coffee"}, "pagination": {"limit": 1},
    })
    assert response.status_code == 404, response.text
    assert await _balance(clients) == before
    assert not [e for e in await _entries(clients) if e["kind"] in ("reserve", "settle", "release")]


async def test_byok_wins_and_is_unmetered(clients, openmart_on):
    await clients.post("/secrets", json={"name": "openmart", "value": "OWN-OPENMART"})
    before = await _balance(clients)
    body = {"tasks": [{"website": "example.invalid", "max_k": 1}]}
    response = await clients.post("/call/openmart.people.find.batch", json=body)
    assert response.status_code == 200, response.text
    echoed = response.json()
    assert echoed["auth"] == "Bearer OWN-OPENMART"
    assert json.loads(echoed["body"]) == body
    assert await _balance(clients) == before
    assert not [e for e in await _entries(clients) if e["kind"] in ("reserve", "settle", "release")]


async def test_byok_lookup_preserves_documented_get_array_body(clients, openmart_on):
    await clients.post("/secrets", json={"name": "openmart", "value": "OWN-OPENMART"})
    ids = ["00000000-0000-4000-8000-000000000001"]
    response = await clients.request(
        "GET", "/call/openmart.businesses.lookup.openmart",
        content=json.dumps(ids), headers={"content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    echoed = response.json()
    assert echoed["auth"] == "Bearer OWN-OPENMART"
    assert json.loads(echoed["body"]) == ids


async def test_capacity_probe_and_policy():
    def probe(request):
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer test"
        return httpx.Response(200, json={
            "balance": 4800,
            "period_start": "2026-09-01T00:00:00Z",
            "period_end": "2026-10-01T00:00:00Z",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(probe)) as client:
        row = await collectors._openmart(client, "test")
    assert row == {
        "value": 4800, "unit": "credits",
        "note": "Monthly subscription balance; current period ends 2026-10-01T00:00:00Z.",
    }
    policy = default_policy("openmart", has_key=True)
    assert policy.capacity_type == "credits"
    assert policy.funding_mode == "subscription"
    assert policy.rate_limit == {"limit": 15, "window_s": 1, "source": "docs"}


def test_company_search_adapter_is_verified_but_not_an_arena_branch():
    cat = store.load()
    adapter = cat.adapters["openmart.companies.search"]
    assert adapter.verified, adapter.verify_note
    assert "openmart.companies.search" in cat.by_id["treg.companies.search"]["routed_children"]
    assert "openmart.companies.enrich" not in cat.by_id["treg.companies.enrich"]["routed_children"]
