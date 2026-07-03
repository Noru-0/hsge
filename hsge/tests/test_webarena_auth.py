"""hsge.webarena.auth: credential precedence and no-op behavior for sites
with no login flow -- pure logic, no real browser/Playwright involved."""

import pytest

from hsge.webarena.auth import DEFAULT_ACCOUNTS, _credentials, ensure_login


def test_credentials_fall_back_to_default_accounts(monkeypatch):
    monkeypatch.delenv("WA_REDDIT_USERNAME", raising=False)
    monkeypatch.delenv("WA_REDDIT_PASSWORD", raising=False)

    username, password = _credentials("reddit")

    assert (username, password) == (
        DEFAULT_ACCOUNTS["reddit"]["username"],
        DEFAULT_ACCOUNTS["reddit"]["password"],
    )


def test_env_credentials_override_default(monkeypatch):
    monkeypatch.setenv("WA_REDDIT_USERNAME", "custom_user")
    monkeypatch.setenv("WA_REDDIT_PASSWORD", "custom_pass")

    assert _credentials("reddit") == ("custom_user", "custom_pass")


def test_ensure_login_is_noop_for_sites_without_a_login_flow(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("must not launch Playwright for a site with no login flow")

    monkeypatch.setattr("playwright.sync_api.sync_playwright", _boom)

    assert ensure_login("wikipedia", "http://wiki.example") is None
    assert ensure_login("map", "http://map.example") is None
    assert ensure_login("some_unknown_site", "http://x.example") is None
