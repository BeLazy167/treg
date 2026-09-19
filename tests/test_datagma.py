from __future__ import annotations

import json

import httpx
import pytest

from treg import api as A
from treg import oauth_providers as providers
from treg.application.call import service as call_service
from treg.application.call import settle as call_settle
from treg.application.call.resolve import MarketplaceCall
from treg.application.call.types import UpstreamResponse
from treg.config import Settings, get_settings
from treg.domain.capacity import collectors, policy
from treg.domain.catalog import store as catalog_store


def _mk(unit_micro=22_580):
    return MarketplaceCall(
        tool=None, upstream="https://gateway.datagma.net/api/ingress/v8/findEmail",
        consumed=set(), provider="datagma", endpoint_id="datagma.people.email.find",
        tier="platform", estimate_micro=unit_micro, cost_type="per_success",
        unit_micro=unit_micro, request_data={},
    )


def _relay(doc):
    async def relay(*args, **kwargs):
        async def stream():
            yield json.dumps(doc).encode()

        async def close():
            return None

        return UpstreamResponse(200, ((b"content-type", b"application/json"),), stream(), close)
    return relay


async def _balance(clients):
    org_id = (await clients.get("/orgs")).json()[0]["org_id"]
    return (await clients.get(f"/orgs/{org_id}/balance")).json()["balance_micro"]


def test_datagma_catalog_has_only_the_five_single_record_tools():
    cat = catalog_store.load()
    endpoints = {eid: ep for eid, ep in cat.by_id.items() if eid.startswith("datagma.")}
    assert set(endpoints) == {
        "datagma.people.email.find", "datagma.people.enrich",
        "datagma.companies.enrich", "datagma.people.phone.find",
        "datagma.people.job-change.detect",
    }
    assert all(ep["scope"] == "any_account" for ep in endpoints.values())
    assert cat.cost_view(endpoints["datagma.people.email.find"]["cost"], "datagma")["usd"] == 0.02258
    assert cat.cost_view(endpoints["datagma.people.phone.find"]["cost"], "datagma")["usd"] == 0.6774
    assert "datagma.people.phone.find" not in cat.adapters
    assert set(endpoints) & {"datagma.people.find", "datagma.people.search"} == set()


@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("1", 22_580), (30, 677_400), ("1.5", 33_870),
    (-1, None), (True, None), ("bad", None), (None, None),
])
def test_datagma_settles_from_reported_credit_burn(raw, expected):
    assert call_settle._observed_cost_micro(
        _mk(), json.dumps({"creditBurn": raw}).encode()) == expected


def test_datagma_registry_and_platform_key(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_DATAGMA", "PLATFORM-DATAGMA")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "datagma")
    provider = providers.get("datagma")
    assert provider.base_url == "https://gateway.datagma.net"
    assert provider.probe_path == "/api/ingress/v1/mine"
    assert Settings(_env_file=None).platform_key_for("datagma") == "PLATFORM-DATAGMA"
    assert providers.platform_bindings(provider) == [{
        "platform_setting": "platform_key_datagma", "injector": "env",
        "location": "query", "name": "apiId", "format": "{secret}",
    }]


async def test_datagma_internal_balance_exposes_only_credit_count(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_DATAGMA", "private-test-key")
    collectors.get_settings.cache_clear()

    def reply(request):
        assert request.url.path == "/api/ingress/v1/mine"
        assert request.url.params["apiId"] == "private-test-key"
        return httpx.Response(200, json={
            "currentCredit": "3002", "email": "owner@example.test", "plan": "private",
        })

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            row = await collectors.provider_balance("datagma", client)
        assert row == {"provider": "datagma", "value": 3002, "unit": "credits",
                       "note": "Prepaid balance; replenished manually"}
        assert "owner" not in str(row) and "plan" not in str(row)
        capacity = policy.default_policy("datagma", has_key=True)
        assert capacity.funding_mode == "manual"
        assert capacity.rate_limit == {"limit": 10, "window_s": 1, "source": "docs"}
    finally:
        collectors.get_settings.cache_clear()


async def test_datagma_balance_failure_does_not_expose_query_key(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_DATAGMA", "private-test-key")
    collectors.get_settings.cache_clear()
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"error": "bad"}, request=request))) as client:
            row = await collectors.provider_balance("datagma", client)
        assert row["value"] is None
        assert "private-test-key" not in str(row)
    finally:
        collectors.get_settings.cache_clear()


async def test_datagma_connection_probe_is_internal_and_generic(clients, monkeypatch):
    def probe(request):
        assert request.url.path == "/api/ingress/v1/mine"
        if request.url.params["apiId"] == "bad":
            return httpx.Response(401, json={"account": "must-not-leak"})
        return httpx.Response(200, json={"currentCredit": "3002", "email": "must-not-leak"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(probe)) as upstream:
        monkeypatch.setattr(A.app.state, "http", upstream)
        bad = await clients.post("/connections/token", json={"provider": "datagma", "token": "bad"})
        assert bad.status_code == 422 and "must-not-leak" not in bad.text
        good = await clients.post("/connections/token", json={"provider": "datagma", "token": "own"})
        assert good.status_code == 200 and "currentCredit" not in good.text and "must-not-leak" not in good.text


async def test_datagma_platform_settles_exact_usage_and_byok_wins(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_DATAGMA", "PLATFORM-DATAGMA")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "datagma")
    get_settings.cache_clear()
    monkeypatch.setattr(call_service, "relay", _relay({
        "email": "person@example.com", "status": "Valid", "creditBurn": "1",
    }))
    before = await _balance(clients)
    response = await clients.get(
        "/call/datagma.people.email.find",
        params={"fullName": "Example Person", "company": "example.com"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-treg-cost-micro"] == "22580"
    assert await _balance(clients) == before - 22_580

    await clients.post("/secrets", json={"name": "datagma", "value": "OWN-DATAGMA"})
    before_byok = await _balance(clients)
    response = await clients.get(
        "/call/datagma.people.email.find",
        params={"fullName": "Example Person", "company": "example.com"},
    )
    assert response.status_code == 200
    assert "x-treg-cost-micro" not in response.headers
    assert await _balance(clients) == before_byok
    get_settings.cache_clear()


def test_datagma_routing_boundary_and_normalized_outputs():
    cat = catalog_store.load()
    assert "datagma.people.email.find" in cat.by_id["treg.people.email.find"]["routed_children"]
    assert "datagma.people.enrich" in cat.by_id["treg.people.enrich"]["routed_children"]
    assert "datagma.companies.enrich" in cat.by_id["treg.companies.enrich"]["routed_children"]
    email = cat.adapters["datagma.people.email.find"]
    assert email.from_upstream({"email": "person@example.com", "status": "Valid"}) == {
        "email": "person@example.com", "verified": True,
    }
    assert email.is_miss({"email": None, "status": "Unknown"})
    person_query, _ = cat.adapters["datagma.people.enrich"].to_upstream({
        "full_name": "Example Person", "domain": "example.com",
    })
    assert person_query == {
        "data": "example.com", "fullName": "Example Person", "companyPremium": False,
        "companyFull": False, "personFull": False, "phoneFull": False,
        "deepTraffic": False, "debug": False,
    }
    company_query, _ = cat.adapters["datagma.companies.enrich"].to_upstream({
        "domain": "example.com",
    })
    assert company_query["data"] == "example.com"
    assert company_query["companyPremium"] is True
    assert company_query["companyFull"] is True
    assert company_query["phoneFull"] is False
