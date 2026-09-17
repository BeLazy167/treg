"""Openmart catalog, connection, capacity, routing, and shared-key safety boundaries."""
import json

import httpx
import pytest

from treg.application.call import service
from treg.application.call import resolve as call_resolution
from treg.application.call import settle as call_settle
from treg.config import get_settings
from treg.domain.catalog import store
from treg.domain.capacity import collectors
from treg.domain.capacity.policy import default_policy
from treg import oauth_providers as P
from test_marketplace_call import _balance, _entries, _fake_relay, _mk, platform_on


@pytest.fixture
def openmart_on(monkeypatch, platform_on):
    monkeypatch.setenv("TREG_PLATFORM_KEY_OPENMART", "PLATFORM-OPENMART")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "openmart")
    get_settings.cache_clear()


def test_surface_separates_platform_sync_reads_from_byok_lifecycles():
    cat = store.load()
    rows = cat.for_provider("openmart")
    assert len(rows) == 16
    assert len({(e["method"], e["path"]) for e in rows}) == 16
    assert {e["id"] for e in rows if cat.platform_eligible(e)} == {
        "openmart.businesses.search",
        "openmart.businesses.lookup.openmart",
        "openmart.businesses.lookup.google-place",
        "openmart.companies.enrich",
        "openmart.companies.search",
    }
    assert all(e.get("verified") and e.get("example_file") for e in rows)
    assert cat.credit_rates["openmart"] == .0298
    assert "openmart.account.balance" not in cat.by_id


def test_pricing_and_lifecycle_boundaries_stay_visible():
    cat = store.load()
    assert cat.by_id["openmart.people.find.batch"]["cost"]["value"] == 11
    assert cat.by_id["openmart.technologies.find.batch"]["cost"]["value"] == 2
    company_email = cat.by_id["openmart.companies.email.find.batch"]
    assert company_email["cost"]["value"] == .3
    assert company_email["cost"]["confidence"] == "documented"
    fast = cat.by_id["openmart.businesses.search.ids"]
    assert fast["cost"]["value"] is None and fast["cost"]["confidence"] == "unknown"
    assert all(cat.by_id[key]["scope"] == "own_account" for key in (
        "openmart.tasks.batch.status", "openmart.tasks.batch.ids", "openmart.tasks.get",
        "openmart.deny-rules.create", "openmart.deny-rules.check",
        "openmart.deny-rules.delete",
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


async def test_unpriced_fast_ids_are_blocked_before_relay_or_money(clients, openmart_on, monkeypatch):
    before = await _balance(clients)

    async def forbidden(*args, **kwargs):
        raise AssertionError("platform guard must precede relay")

    monkeypatch.setattr(service, "relay", forbidden)
    response = await clients.post("/call/openmart.businesses.search.ids", json={
        "query": "coffee", "limit": 1,
    })
    assert response.status_code == 404, response.text
    assert await _balance(clients) == before
    assert not [e for e in await _entries(clients) if e["kind"] in ("reserve", "settle", "release")]


@pytest.mark.parametrize(("endpoint", "body", "expected"), [
    ("openmart.businesses.search", b'[{"id":"1"},{"id":"2"},{"id":"3"}]', 3),
    ("openmart.businesses.search", b'{"data":[{"id":"1"}]}', 1),
    ("openmart.businesses.search", b'{"data":[]}', 0),
    ("openmart.companies.enrich", b'[]', 0),
    ("openmart.companies.search", b'{"data":[{},{}]}', 2),
    ("openmart.businesses.lookup.openmart", b'{"a":{},"b":{}}', 2),
])
def test_declarative_result_count_supports_documented_shapes(endpoint, body, expected):
    mk = _mk("openmart", endpoint_id=endpoint, cost_type="per_result", unit_micro=8_940)
    assert call_settle._observed_cost_micro(mk, body) == expected * 8_940


def test_declarative_result_count_never_guesses_an_undeclared_shape():
    search = _mk("openmart", endpoint_id="openmart.businesses.search",
                 cost_type="per_result", unit_micro=8_940)
    lookup = _mk("openmart", endpoint_id="openmart.businesses.lookup.openmart",
                 cost_type="per_result", unit_micro=8_940)
    assert call_settle._observed_cost_micro(search, b'{"data":{}}') is None
    assert call_settle._observed_cost_micro(lookup, b'[]') is None


def test_openmart_reservations_use_endpoint_bounds_and_input_cardinality():
    cat = store.load()

    def estimate(endpoint, body):
        cost = cat.cost_view(cat.by_id[endpoint]["cost"], "openmart")
        return call_resolution._platform_estimate_micro(cost, {}, json.dumps(body).encode())

    assert estimate("openmart.businesses.search", {"query": "coffee", "limit": 3}) == 3 * 8_940
    assert estimate("openmart.companies.search", {"pagination": {"limit": 500}}) == 500 * 8_940
    assert estimate("openmart.businesses.lookup.openmart", ["a", "b", "c"]) == 3 * 8_940


async def test_platform_search_settles_from_returned_rows(clients, openmart_on, monkeypatch):
    rows = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    monkeypatch.setattr(service, "relay", _fake_relay(200, json.dumps(rows).encode()))
    before = await _balance(clients)
    response = await clients.post("/call/openmart.businesses.search", json={
        "query": "coffee", "limit": 5,
    })
    assert response.status_code == 200, response.text
    assert await _balance(clients) == before - 3 * 8_940
    money = [e for e in await _entries(clients) if e["kind"] in ("reserve", "settle", "release")]
    assert [e["kind"] for e in money[:2]] == ["settle", "reserve"]


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


def test_company_search_adapter_is_verified_and_platform_routed_but_not_enrich_arena():
    cat = store.load()
    adapter = cat.adapters["openmart.companies.search"]
    assert adapter.verified, adapter.verify_note
    assert "openmart.companies.search" in cat.by_id["treg.companies.search"]["routed_children"]
    assert cat.platform_eligible(cat.by_id["openmart.companies.search"])
    assert "openmart.companies.enrich" not in cat.by_id["treg.companies.enrich"]["routed_children"]
