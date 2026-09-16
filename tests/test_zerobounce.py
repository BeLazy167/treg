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


def _mk():
    return MarketplaceCall(
        tool=None,
        upstream="https://api.zerobounce.net/v2/validate",
        consumed=set(),
        provider="zerobounce",
        endpoint_id="zerobounce.people.email.verify",
        tier="platform",
        estimate_micro=13_800,
        cost_type="per_success",
        unit_micro=13_800,
        request_data={},
    )


def _relay(status: int, doc: dict):
    async def relay(*args, **kwargs):
        async def stream():
            yield json.dumps(doc).encode()

        async def close():
            return None

        return UpstreamResponse(
            status,
            ((b"content-type", b"application/json"),),
            stream(),
            close,
        )

    return relay


async def _balance(clients):
    org_id = (await clients.get("/orgs")).json()[0]["org_id"]
    response = await clients.get(f"/orgs/{org_id}/balance")
    return response.json()["balance_micro"]


def test_zerobounce_catalog_exposes_only_the_safe_first_surface():
    catalog = catalog_store.load()
    endpoints = {eid: ep for eid, ep in catalog.by_id.items() if eid.startswith("zerobounce.")}
    assert set(endpoints) == {"zerobounce.people.email.verify"}
    validation = endpoints["zerobounce.people.email.verify"]
    assert validation["method"] == "GET"
    assert validation["path"] == "/v2/validate"
    assert catalog.cost_view(validation["cost"], "zerobounce")["usd"] == 0.0138
    assert "zerobounce.people.email.verify.bulk" not in endpoints


def test_zerobounce_registry_and_platform_key(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "PLATFORM-ZEROBOUNCE")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "zerobounce")
    provider = providers.get("zerobounce")
    settings = Settings(_env_file=None)
    assert provider.base_url == "https://api.zerobounce.net"
    assert provider.probe_path.startswith("/v2/getapiusage?")
    assert settings.platform_key_for("zerobounce") == "PLATFORM-ZEROBOUNCE"
    assert providers.platform_bindings(provider) == [{
        "platform_setting": "platform_key_zerobounce",
        "injector": "env",
        "location": "query",
        "name": "api_key",
        "format": "{secret}",
    }]


async def test_zerobounce_connection_rejects_bad_key_and_accepts_valid_key(clients, monkeypatch):
    def probe(request):
        assert request.url.path == "/v2/getapiusage"
        assert request.url.params["start_date"] == "2026-01-01"
        assert request.url.params["end_date"] == "2026-12-31"
        key = request.url.params["api_key"]
        if key == "bad-key":
            return httpx.Response(403, json={"error": "invalid api key"})
        return httpx.Response(200, json={"total": 0, "status_valid": 0})

    async with httpx.AsyncClient(transport=httpx.MockTransport(probe)) as upstream:
        monkeypatch.setattr(A.app.state, "http", upstream)
        bad = await clients.post(
            "/connections/token", json={"provider": "zerobounce", "token": "bad-key"})
        assert bad.status_code == 422
        good = await clients.post(
            "/connections/token", json={"provider": "zerobounce", "token": "own-key"})
        assert good.status_code == 200, good.text


@pytest.mark.parametrize("value,expected", [(0, 0), (71, 71), ("5000", 5000)])
async def test_zerobounce_capacity_accepts_numeric_credit_balances(monkeypatch, value, expected):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "private-test-key")
    collectors.get_settings.cache_clear()

    def reply(request):
        assert request.url.path == "/v2/getcredits"
        assert request.url.params["api_key"] == "private-test-key"
        return httpx.Response(200, json={"Credits": value})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            row = await collectors.provider_balance("zerobounce", client)
        assert row["value"] == expected
        assert row["unit"] == "validation credits"
        assert "Auto-Pay" in row["note"]
    finally:
        collectors.get_settings.cache_clear()


@pytest.mark.parametrize("status,value", [
    (200, -1), (200, "-1"), (200, True), (200, 12.5), (200, "12.5"), (200, "bad"),
    (403, None),
])
async def test_zerobounce_capacity_rejects_invalid_answers_without_exposing_key(
    monkeypatch, status, value,
):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "private-test-key")
    collectors.get_settings.cache_clear()

    def reply(request):
        return httpx.Response(status, json={"Credits": value}, request=request)

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            row = await collectors.provider_balance("zerobounce", client)
        assert row["value"] is None
        assert row["note"]
        assert "private-test-key" not in str(row)
    finally:
        collectors.get_settings.cache_clear()


def test_zerobounce_capacity_policy_preserves_vendor_auto_pay():
    row = policy.default_policy("zerobounce", has_key=True)
    assert row.capacity_type == "credits"
    assert row.funding_mode == "auto_recharge"
    assert row.source == "api"
    assert row.auto_funding_enabled is True
    assert row.rate_limit == {"limit": 25, "window_s": 1, "source": "policy"}


def test_zerobounce_unknown_is_a_free_miss_and_verdicts_are_answers():
    adapter = catalog_store.load().adapters["zerobounce.people.email.verify"]
    assert call_settle._observed_cost_micro(_mk(), b'{"status":"unknown"}') == 0
    assert call_settle._observed_cost_micro(_mk(), b'{"status":"invalid"}') is None
    assert adapter.is_miss({"status": "unknown"})
    assert adapter.is_miss({})
    for status, valid in (("valid", True), ("invalid", False), ("catch-all", False),
                          ("spamtrap", False), ("abuse", False), ("do_not_mail", False)):
        doc = {"status": status}
        assert not adapter.is_miss(doc)
        assert adapter.from_upstream(doc) == {"valid": valid, "status": status}


async def test_zerobounce_platform_settlement_release_and_byok_precedence(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "PLATFORM-ZEROBOUNCE")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "zerobounce")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(call_service, "relay", _relay(200, {
            "address": "bad@example.com", "status": "invalid", "sub_status": "mailbox_not_found",
        }))
        before = await _balance(clients)
        response = await clients.get(
            "/call/zerobounce.people.email.verify", params={"email": "bad@example.com"})
        assert response.status_code == 200, response.text
        assert response.headers["x-treg-cost-micro"] == "13800"
        assert await _balance(clients) == before - 13_800

        monkeypatch.setattr(call_service, "relay", _relay(200, {
            "address": "wait@example.com", "status": "unknown", "sub_status": "greylisted",
        }))
        before_unknown = await _balance(clients)
        response = await clients.get(
            "/call/zerobounce.people.email.verify", params={"email": "wait@example.com"})
        assert response.status_code == 200
        assert response.headers["x-treg-cost-micro"] == "0"
        assert await _balance(clients) == before_unknown

        monkeypatch.setattr(call_service, "relay", _relay(500, {"error": "temporary"}))
        before_failure = await _balance(clients)
        response = await clients.get(
            "/call/zerobounce.people.email.verify", params={"email": "fail@example.com"})
        assert response.status_code == 500
        assert await _balance(clients) == before_failure

        await clients.post(
            "/secrets", json={"name": "zerobounce", "value": "OWN-ZEROBOUNCE"})
        monkeypatch.setattr(call_service, "relay", _relay(200, {
            "address": "good@example.com", "status": "valid", "sub_status": "",
        }))
        before_byok = await _balance(clients)
        response = await clients.get(
            "/call/zerobounce.people.email.verify", params={"email": "good@example.com"})
        assert response.status_code == 200
        assert "x-treg-cost-micro" not in response.headers
        assert await _balance(clients) == before_byok
    finally:
        get_settings.cache_clear()


async def test_zerobounce_joins_email_verification_arena(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "PLATFORM-ZEROBOUNCE")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "zerobounce")
    get_settings.cache_clear()
    try:
        response = await clients.post("/arena/plans", json={
            "capability": "people.email.verify",
            "identity": {"email": "valid@example.com"},
            "mode": "compare",
            "providers": ["zerobounce"],
            "max_cost_micro": 20_000,
        })
        assert response.status_code == 200, response.text
        quote = response.json()
        assert quote["providers"][0]["provider"] == "zerobounce"
        assert quote["providers"][0]["endpoint_id"] == "zerobounce.people.email.verify"
        assert quote["estimate_micro"] == 13_800
    finally:
        get_settings.cache_clear()


async def test_zerobounce_serves_the_existing_email_verification_route(clients, monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ZEROBOUNCE", "PLATFORM-ZEROBOUNCE")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "zerobounce")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(call_service, "relay", _relay(200, {
            "address": "valid@example.com", "status": "valid", "sub_status": "",
        }))
        response = await clients.post(
            "/call/treg.people.email.verify", json={"email": "valid@example.com"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["output"]["valid"] is True
        assert body["output"]["status"] == "valid"
        assert body["_treg"]["served_by"] == "zerobounce.people.email.verify"
    finally:
        get_settings.cache_clear()
