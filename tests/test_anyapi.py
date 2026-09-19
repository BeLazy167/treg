"""AnyAPI's key-only catalog is platform-eligible on every row and settles on the reported charge."""
import pytest

from treg.config import get_settings
from treg.domain.catalog import store
from treg.oauth_providers import get, platform_bindings


@pytest.fixture
def anyapi_on(monkeypatch):
    monkeypatch.setenv("TREG_PLATFORM_KEY_ANYAPI", "TEST-PLATFORM-ANYAPI")
    monkeypatch.setenv("TREG_PLATFORM_PROVIDERS", "anyapi")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_anyapi_catalog_is_platform_eligible_and_settles_on_cost_usd(anyapi_on):
    catalog = store.load()
    rows = [ep for ep in catalog.endpoints if ep["provider"] == "anyapi"]
    assert len(rows) >= 36
    for ep in rows:
        assert ep["method"] == "POST" and ep["path"].startswith("/v1/run/"), ep["id"]
        assert catalog.platform_eligible(ep), ep["id"]
        assert ep["cost"]["reported_charge"] == {"path": "costUsd", "unit": "usd"}, ep["id"]
    assert get_settings().platform_key_for("anyapi") == "TEST-PLATFORM-ANYAPI"
    assert get("anyapi").probe_path == "/v1/balance"
    # The platform key rides in the same header the user's own key does.
    assert [b["name"] for b in platform_bindings(get("anyapi"))] == ["X-API-Key"]
