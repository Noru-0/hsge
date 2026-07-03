# Design: login/auth for the WebArena runtime

Date: 2026-07-03

## Purpose

`hsge/webarena/browser.py`'s `WebArenaBrowser` does zero authentication today
-- every `browser_factory(url)` call in `runtime.py`'s frontier loop creates a
fresh, logged-out `browsergym/openended` env. Any `[MOD]` task (post, vote,
add to cart, checkout) or account-only page (profile, dashboard) either fails
or hits a login wall. This adds login support for the four account-gated
WebArena sites (reddit, gitlab, shopping, shopping_admin; wikipedia/map need
no login) using a **login-once, cache-the-session** approach rather than
logging in on every node visit.

## Why not reuse `browsergym.webarena.instance.WebArenaInstance` directly

It ships the exact same per-site Playwright login flows we want (`ui_login`),
but its constructor hard-`assert`s that **all seven** `WA_REDDIT`,
`WA_SHOPPING`, `WA_SHOPPING_ADMIN`, `WA_GITLAB`, `WA_WIKIPEDIA`, `WA_MAP`,
`WA_HOMEPAGE` are present and non-empty (via the `webarena` pip package's
`browser_env/env_config.py`), even though HSGE only ever explores one site
per run and only sets `WA_<SITE>` for that one site today. Rather than
faking placeholder env vars for sites not in use to satisfy someone else's
unrelated assert, HSGE gets its own small `auth.py` with the same login
flows, keyed only off the site actually being run.

## Confirmed decisions

- Scope: all four account-gated sites (reddit, gitlab, shopping,
  shopping_admin), even though a given run only touches one (`run.site`).
- Credentials: new `.env` vars `WA_<SITE>_USERNAME` / `WA_<SITE>_PASSWORD`,
  falling back to the standard published WebArena benchmark test accounts
  when unset (so a stock instance needs zero new `.env` entries).
- Caching: login live once, persist Playwright `storage_state` (cookies) to
  `.auth/<site>_state.json`, reuse it for every subsequent browser context in
  the run (and across runs) until it's found expired.

## New module: `hsge/webarena/auth.py`

```python
DEFAULT_ACCOUNTS = {
    "reddit": {"username": "MarvelsGrantMan136", "password": "test1234"},
    "gitlab": {"username": "byteblaze", "password": "hello1234"},
    "shopping": {"username": "emma.lopez@gmail.com", "password": "Password.123"},
    "shopping_admin": {"username": "admin", "password": "admin1234"},
}
```
(the standard published benchmark accounts, ported as documented defaults --
not secrets in the sense of being novel, but still overridable per-instance.)

- `_credentials(site) -> (username, password)`: reads
  `WA_<SITE>_USERNAME`/`WA_<SITE>_PASSWORD` from the environment, falling
  back to `DEFAULT_ACCOUNTS[site]`.
- `_login_reddit/_login_gitlab/_login_shopping/_login_shopping_admin(page, username, password)`:
  one function per site, each the same fill+click sequence as
  `browsergym.webarena.instance.WebArenaInstance.ui_login` /
  `references/webarena-main/browser_env/auto_login.py` (identical selectors
  -- these are stable, official benchmark-page selectors, ported not
  reinvented).
- `_CHECKS = {site: (path_template, keyword_or_None)}`: the same
  "am I still logged in" table from `auto_login.py`'s `is_expired`:
  - `reddit`: `/user/{username}/account`, keyword `"Delete"` (own account
    page shows a "Delete account" affordance only when authenticated as that
    user)
  - `gitlab`: `/-/profile`, exact-URL match (no keyword -- redirected to the
    sign-in page if the session is dead)
  - `shopping`: `/wishlist/`, exact-URL match
  - `shopping_admin`: `/dashboard`, keyword `"Dashboard"`
- `is_logged_in(storage_state_path, root_url, site) -> bool`: `False` if the
  file doesn't exist; otherwise opens a throwaway Playwright browser +
  context with that `storage_state`, navigates to the site's check URL
  (reddit's template needs the username, so this calls `_credentials(site)`
  itself rather than taking it as a separate parameter), and evaluates per
  `_CHECKS[site]`.
- `ensure_login(site, root_url, auth_dir=".auth", headless=True) -> str | None`:
  the entry point.
  - Returns `None` immediately for `wikipedia`/`map`/any site not in
    `_CHECKS` (no login flow, nothing to do).
  - If `.auth/<site>_state.json` exists and `is_logged_in(...)` is `True`,
    returns that path unchanged.
  - Otherwise: launches a throwaway Playwright browser, navigates to the
    site's login page, runs the site's login function, then
    `context.storage_state(path=".auth/<site>_state.json")`, closes the
    browser, and returns the path.

## Wiring

- `hsge/webarena/browser.py`: `WebArenaBrowser.__init__` gains
  `storage_state: str | None = None`. When set, it's merged into the
  existing `env_kwargs["pw_context_kwargs"]` dict alongside the current
  `extra_http_headers` handling (both can be present at once) -- no change
  needed to `reset()`/`observation()`/`act()`.
- `run_webarena.py::main()` (real-run branch only; dry-run is untouched):
  right after resolving `root_url`/`site`, and after `perform_full_reset` (if
  it ran), call `auth_path = ensure_login(site, root_url, headless=not headed)`;
  `browser_factory = lambda url: WebArenaBrowser(url, headless=not headed, storage_state=auth_path)`.
- If `full_reset_url` actually ran this invocation, delete any cached
  `.auth/<site>_state.json` *before* calling `ensure_login` -- a full reset
  reseeds the instance's database, which can invalidate a previously-cached
  session, so force a fresh login against the just-reset instance.
- `--read-only` and `--dry-run` are unaffected: read-only still logs in
  (login itself isn't a write; it's what makes account-only *read* pages
  like one's own profile reachable), dry-run never touches real auth.

## Config / secrets

- New optional `.env` vars: `WA_<SITE>_USERNAME` / `WA_<SITE>_PASSWORD` for
  `SITE` in `REDDIT`/`GITLAB`/`SHOPPING`/`SHOPPING_ADMIN` -- optional,
  default to the standard benchmark accounts above when unset.
- No `config.yaml` changes: login is automatic whenever `run.site` is one of
  the four account-gated sites; no on/off toggle in this iteration (listed
  under Out of scope).
- `.auth/` added to `.gitignore` -- cached cookies are live session
  credentials and must never be committed.

## Testing plan

- No real WebArena instance is reachable from this sandbox (LAN-only), so
  end-to-end login can't be exercised here. Unit-test the pure-logic parts
  with no browser involved:
  - `_credentials()` env-var-vs-default precedence (role/site override vs
    `DEFAULT_ACCOUNTS` fallback), mirroring the style of the existing
    `_effective_llm_config` precedence tests.
  - `ensure_login()` returns `None` immediately for `wikipedia`, `map`, and
    an unrecognized site string, without attempting to launch Playwright at
    all (assert this via monkeypatching a Playwright launch function to
    raise if called, so the test fails loudly if that guarantee breaks).
- Manual (by the user, against the real instance): run
  `python run_webarena.py`, confirm `.auth/<site>_state.json` is created,
  and confirm a second run reuses it (no visible re-login, `ensure_login`
  logs that it reused the cached session).

## Out of scope

- A `config.yaml` toggle to disable auto-login entirely.
- Multi-account / credential rotation (one fixed account per site, matching
  the benchmark's own design).
- Sites with no login flow (wikipedia, map) -- `ensure_login` is a no-op.
- Any change to the exploration/discovery pipeline itself; this is purely an
  auth layer under `WebArenaBrowser`.
