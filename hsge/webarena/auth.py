"""Login/auth for the WebArena runtime.

Login once per site, cache the resulting Playwright storage_state (cookies),
and reuse it across every browser context in a run instead of re-logging in
on every node visit -- runtime.py's frontier loop constructs a fresh browser
per node (up to max_nodes times), so a live login on every visit would be
slow and risky against a real, possibly shared instance.

Login flows are ported from browsergym.webarena.instance.WebArenaInstance's
ui_login (same selectors as references/webarena-main/browser_env/auto_login.py).
HSGE writes its own copy instead of constructing WebArenaInstance directly:
that class's __init__ hard-requires ALL of WA_REDDIT/SHOPPING/SHOPPING_ADMIN/
GITLAB/WIKIPEDIA/MAP/HOMEPAGE to be set, even though a given HSGE run only
ever explores one site.
"""
from __future__ import annotations

import os

# The standard published WebArena benchmark test accounts; overridable per
# instance via WA_<SITE>_USERNAME / WA_<SITE>_PASSWORD in .env.
DEFAULT_ACCOUNTS = {
    "reddit": {"username": "MarvelsGrantMan136", "password": "test1234"},
    "gitlab": {"username": "byteblaze", "password": "hello1234"},
    "shopping": {"username": "emma.lopez@gmail.com", "password": "Password.123"},
    "shopping_admin": {"username": "admin", "password": "admin1234"},
}

# site -> (path relative to root_url to check, keyword that must be in the
# page's content, or None to instead require an exact URL match).
_CHECKS = {
    "reddit": ("/user/{username}/account", "Delete"),
    "gitlab": ("/-/profile", None),
    "shopping": ("/wishlist/", None),
    "shopping_admin": ("/dashboard", "Dashboard"),
}


def _credentials(site: str) -> tuple[str, str]:
    prefix = f"WA_{site.upper()}"
    default = DEFAULT_ACCOUNTS.get(site, {})
    username = os.environ.get(f"{prefix}_USERNAME") or default.get("username", "")
    password = os.environ.get(f"{prefix}_PASSWORD") or default.get("password", "")
    return username, password


def _login_reddit(page, root_url: str, username: str, password: str) -> None:
    page.goto(root_url)
    page.get_by_role("link", name="Log in").click()
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()


def _login_gitlab(page, root_url: str, username: str, password: str) -> None:
    page.goto(f"{root_url}/users/sign_in")
    page.get_by_label("Username or email").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


def _login_shopping(page, root_url: str, username: str, password: str) -> None:
    page.goto(f"{root_url}/customer/account/login/")
    page.get_by_label("Email", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign In").click()


def _login_shopping_admin(page, root_url: str, username: str, password: str) -> None:
    page.goto(root_url)
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


_LOGIN_FLOWS = {
    "reddit": _login_reddit,
    "gitlab": _login_gitlab,
    "shopping": _login_shopping,
    "shopping_admin": _login_shopping_admin,
}


def is_logged_in(storage_state_path: str, root_url: str, site: str) -> bool:
    """Load a cached storage_state and check whether the session is still valid."""
    if not os.path.exists(storage_state_path):
        return False
    check = _CHECKS.get(site)
    if not check:
        return False
    path_template, keyword = check
    username, _ = _credentials(site)
    check_url = root_url.rstrip("/") + path_template.format(username=username)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=storage_state_path)
            page = context.new_page()
            try:
                page.goto(check_url, timeout=15000)
            except Exception:
                return False
            return (keyword in page.content()) if keyword else (page.url == check_url)
        finally:
            browser.close()


def ensure_login(site: str, root_url: str, auth_dir: str = ".auth",
                  headless: bool = True) -> str | None:
    """Return a path to a valid storage_state.json for `site`, logging in
    fresh (and caching the result) if none exists yet or it has expired.

    None if `site` has no login flow (e.g. wikipedia, map).
    """
    if site not in _LOGIN_FLOWS:
        return None
    os.makedirs(auth_dir, exist_ok=True)
    path = os.path.join(auth_dir, f"{site}_state.json")

    if is_logged_in(path, root_url, site):
        print(f"[auth] reusing cached session for {site} ({path})")
        return path

    username, password = _credentials(site)
    print(f"[auth] logging in to {site} as {username!r} -> {path}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = browser.new_context()
            page = context.new_page()
            _LOGIN_FLOWS[site](page, root_url, username, password)
            context.storage_state(path=path)
        finally:
            browser.close()
    return path
