from __future__ import annotations

import json

import httpx
import pytest

from treg import api as A
from treg import oauth_providers as providers
from treg.application.call import service as call_service
from treg.application.call.types import UpstreamResponse
from treg.config import Settings, get_settings
from treg.domain.capacity import collectors, policy
from treg.domain.catalog import store as catalog_store


async def _balance(clients):
    org_id = (await clients.get("/orgs")).json()[0]["org_id"]
    return (await clients.get(f"/orgs/{org_id}/balance")).json()["balance_micro"]


def _relay(status: int, doc: dict):
    async def relay(*args, **kwargs):
        async def stream():
            yield json.dumps(doc).encode()

        async def close():
            return None

        return UpstreamResponse(status, ((b"content-type", b"application/json"),), stream(), close)
    return relay


def test_aiark_catalog_covers_the_selected_documented_surface():
    catalog = catalog_store.load()
    endpoints = {eid: ep for eid, ep in catalog.by_id.items() if eid.startswith("aiark.")}
    assert set(endpoints) == {
        "aiark.people.search", "aiark.people.preview", "aiark.companies.search",
        "aiark.people.email.find", "aiark.people.phone.find", "aiark.people.enrich",
        "aiark.people.personality.analyze", "aiark.lists.upsert",
        "aiark.people.export.start", "aiark.people.export.results",
        "aiark.people.export.statistics", "aiark.people.export.submissions",
        "aiark.people.export.webhook.resend", "aiark.people.email.find.bulk",
        "aiark.people.email.find.bulk.results", "aiark.people.email.find.bulk.statistics",
        "aiark.people.email.find.bulk.submissions",
        "aiark.people.email.find.bulk.webhook.resend",
    }
    assert not any(ep["path"] in {
        "/v1/payments/credits", "/v1/people/export/single", "/v1/people/mobile-phone-finder",
    } for ep in endpoints.values())
    assert all(ep.get("platform_blocked") for eid, ep in endpoints.items()
               if ".export." in eid or ".bulk" in eid or eid == "aiark.lists.upsert")
    assert endpoints["aiark.people.search"]["input"]["body"]["size"]["enum"] == [1]
    assert endpoints["aiark.people.search"]["platform_request"] == {"body.size": 1}
    assert catalog.cost_view(endpoints["aiark.people.email.find"]["cost"], "aiark")["usd"] == 0.005267
    assert catalog.cost_view(endpoints["aiark.people.phone.find"]["cost"], "aiark")["usd"] == 0.026335


def test_aiark_registry_and_platform_key(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_AIARK", "PLATFORM-AIARK")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "aiark")
    provider = providers.get("aiark")
    settings = Settings(_env_file=None)
    assert provider.base_url == "https://api.ai-ark.com/api/developer-portal"
    assert provider.probe_path == "/v1/payments/credits"
    assert provider.probe_method == "GET"
    assert settings.platform_key_for("aiark") == "PLATFORM-AIARK"
    assert providers.platform_bindings(provider) == [{
        "platform_setting": "platform_key_aiark", "injector": "env",
        "location": "header", "name": "X-TOKEN", "format": "{secret}",
    }]


async def test_aiark_connection_rejects_bogus_and_accepts_valid(clients, monkeypatch):
    def probe(request):
        assert request.url.path == "/api/developer-portal/v1/payments/credits"
        key = request.headers["x-token"]
        if key == "bad":
            return httpx.Response(401, json={"error": "Unauthorized"})
        return httpx.Response(200, json={"total": 15000})

    async with httpx.AsyncClient(transport=httpx.MockTransport(probe)) as upstream:
        monkeypatch.setattr(A.app.state, "http", upstream)
        bad = await clients.post("/connections/token", json={"provider": "aiark", "token": "bad"})
        assert bad.status_code == 422
        good = await clients.post("/connections/token", json={"provider": "aiark", "token": "own-key"})
        assert good.status_code == 200, good.text


@pytest.mark.parametrize("remaining,expected", [(15000, 15000), (0, 0), (15000.5, 15000.5), (-1, None), (True, None)])
async def test_aiark_balance_collector_uses_total(remaining, expected):
    def serve(request):
        assert request.url.path == "/api/developer-portal/v1/payments/credits"
        assert request.headers["x-token"] == "test-key"
        return httpx.Response(200, json={"total": remaining})

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as upstream:
        if expected is None:
            with pytest.raises(ValueError):
                await collectors._aiark(upstream, "test-key")
        else:
            row = await collectors._aiark(upstream, "test-key")
            assert row["value"] == expected
            assert row["unit"] == "credits"
            assert "roll over" in row["note"]


def test_aiark_capacity_policy_uses_subscription_and_documented_rate():
    row = policy.default_policy("aiark", has_key=True)
    assert row.capacity_type == "monthly_quota"
    assert row.funding_mode == "quota_reset"
    assert row.auto_funding_enabled is False
    assert row.rate_limit == {"limit": 5, "window_s": 1, "source": "docs"}


def test_aiark_routing_adapters_are_verified_and_bounded():
    catalog = catalog_store.load()
    expected = {
        "aiark.people.search", "aiark.companies.search", "aiark.people.email.find",
        "aiark.people.phone.find", "aiark.people.enrich",
    }
    assert {eid for eid in expected if catalog.adapters[eid].verified} == expected
    _, people = catalog.adapters["aiark.people.search"].to_upstream({"company_domain": "example.com"})
    _, companies = catalog.adapters["aiark.companies.search"].to_upstream({"domain": "example.com"})
    assert people == {"account": {"domain": {"any": {"include": ["example.com"]}}}, "page": 0, "size": 1}
    assert companies == people


async def test_aiark_platform_settles_hit_releases_miss_and_byok_wins(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_AIARK", "PLATFORM-AIARK")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "aiark")
    get_settings.cache_clear()
    hit = {
        "status": 200, "error": None,
        "data": {"profile": {"first_name": "Jane", "last_name": "Example"},
                 "email": {"output": [{"address": "jane@example.com", "status": "VALID"}]},
                 "link": {"linkedin": "https://www.linkedin.com/in/example"}},
    }
    monkeypatch.setattr(call_service, "relay", _relay(200, hit))
    before = await _balance(clients)
    response = await clients.post("/call/aiark.people.email.find", json={
        "url": "https://www.linkedin.com/in/example",
    })
    assert response.status_code == 200, response.text
    assert response.headers["x-treg-cost-micro"] == "5267"
    assert await _balance(clients) == before - 5267

    monkeypatch.setattr(call_service, "relay", _relay(200, {"status": 200, "error": None, "data": None}))
    before_miss = await _balance(clients)
    response = await clients.post("/call/aiark.people.email.find", json={
        "url": "https://www.linkedin.com/in/missing",
    })
    assert response.status_code == 200
    assert response.headers["x-treg-cost-micro"] == "0"
    assert await _balance(clients) == before_miss

    await clients.post("/secrets", json={"name": "aiark", "value": "OWN-AIARK"})
    before_byok = await _balance(clients)
    response = await clients.post("/call/aiark.people.email.find", json={
        "url": "https://www.linkedin.com/in/example",
    })
    assert response.status_code == 200
    assert "x-treg-cost-micro" not in response.headers
    assert await _balance(clients) == before_byok
    get_settings.cache_clear()


async def test_aiark_platform_releases_rejected_request_and_enforces_search_bound(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_AIARK", "PLATFORM-AIARK")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "aiark")
    get_settings.cache_clear()
    monkeypatch.setattr(call_service, "relay", _relay(400, {"status": 400, "error": "invalid input"}))
    before = await _balance(clients)
    response = await clients.post("/call/aiark.people.email.find", json={})
    assert response.status_code == 400
    assert await _balance(clients) == before

    response = await clients.post("/call/aiark.people.search", json={
        "account": {"domain": {"any": {"include": ["example.com"]}}}, "page": 0, "size": 2,
    })
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "catalog_parameter_invalid"
    assert await _balance(clients) == before

    get_settings.cache_clear()


async def test_aiark_email_finder_appears_in_arena(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_AIARK", "PLATFORM-AIARK")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "aiark")
    get_settings.cache_clear()
    response = await clients.post("/arena/plans", json={
        "capability": "people.email.find",
        "identity": {"linkedin_url": "https://www.linkedin.com/in/example"},
        "mode": "compare", "providers": ["aiark"], "max_cost_micro": 100_000,
    })
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote["providers"][0]["endpoint_id"] == "aiark.people.email.find"
    assert quote["estimate_micro"] == 5267
    get_settings.cache_clear()
