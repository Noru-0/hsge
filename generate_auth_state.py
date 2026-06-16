"""
Generate Playwright storageState for WebArena sites.

Usage:
    # Generate state for shopping site (default)
    python generate_auth_state.py

    # Generate state for a specific site with custom credentials
    python generate_auth_state.py --url "http://host:7770/login" \
        --username "user@example.com" --password "pass123" \
        --output ".auth/shopping_state.json" \
        --username-field "input[name='email']" \
        --password-field "input[name='pwd']" \
        --submit-button "button[type='submit']" \
        --success-url "http://host:7770/"

    # Generate state for all WebArena sites at once
    python generate_auth_state.py --all-sites

When the script completes, pass the output file to run_webarena.py:
    python run_webarena.py --storage-state ".auth/shopping_state.json" ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


# ---------------------------------------------------------------------------
# .env loader (lightweight, no extra dependency)
# ---------------------------------------------------------------------------
def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no override)."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k not in os.environ:
                os.environ[k] = v


_load_dotenv()


# ---------------------------------------------------------------------------
# Defaults from .env (or fallback values)
# ---------------------------------------------------------------------------
DEFAULT_URL = os.environ.get("WA_SHOPPING", "http://192.168.1.31:7770")
DEFAULT_USERNAME = os.environ.get("WA_ACCOUNT_SHOPPING_USERNAME", "emma.lopez@gmail.com")
DEFAULT_PASSWORD = os.environ.get("WA_ACCOUNT_SHOPPING_PASSWORD", "Password.123")
DEFAULT_OUTPUT = ".auth/shopping_state.json"

# Common login field selectors for WebArena sites
SITE_CONFIGS = {
    "shopping": {
        "url": os.environ.get("WA_SHOPPING", "http://192.168.1.31:7770"),
        "login_path": "/customer/account/login",
        "username_field": "input[name='login[username]']",
        "password_field": "input[name='login[password]']",
        "submit_button": "button[type='submit']",
        "success_url": os.environ.get("WA_SHOPPING", "http://192.168.1.31:7770") + "/",
        "username": os.environ.get("WA_ACCOUNT_SHOPPING_USERNAME", "emma.lopez@gmail.com"),
        "password": os.environ.get("WA_ACCOUNT_SHOPPING_PASSWORD", "Password.123"),
        "output": ".auth/shopping_state.json",
    },
    "shopping_admin": {
        "url": os.environ.get("WA_SHOPPING_ADMIN", "http://192.168.1.31:7780/admin"),
        "login_path": "/admin",
        "username_field": "input[name='login[username]']",
        "password_field": "input[name='login[password]']",
        "submit_button": "button[type='submit']",
        "success_url": os.environ.get("WA_SHOPPING_ADMIN", "http://192.168.1.31:7780/admin/dashboard"),
        "username": os.environ.get("WA_ACCOUNT_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("WA_ACCOUNT_ADMIN_PASSWORD", "admin1234"),
        "output": ".auth/shopping_admin_state.json",
    },
    "reddit": {
        "url": os.environ.get("WA_REDDIT", "http://192.168.1.31:9999"),
        "login_path": "/login",
        "username_field": "input[name='user']",
        "password_field": "input[name='pass']",
        "submit_button": "button[type='submit']",
        "success_url": os.environ.get("WA_REDDIT", "http://192.168.1.31:9999") + "/",
        "username": os.environ.get("WA_ACCOUNT_REDDIT_USERNAME", "MarvelsGrantMan136"),
        "password": os.environ.get("WA_ACCOUNT_REDDIT_PASSWORD", "test1234"),
        "output": ".auth/reddit_state.json",
    },
    "gitlab": {
        "url": os.environ.get("WA_GITLAB", "http://192.168.1.31:8023"),
        "login_path": "/users/sign_in",
        "username_field": "input[name='user[login]']",
        "password_field": "input[name='user[password]']",
        "submit_button": "button[type='submit']",
        "success_url": os.environ.get("WA_GITLAB", "http://192.168.1.31:8023") + "/",
        "username": os.environ.get("WA_ACCOUNT_GITLAB_USERNAME", "byteblaze"),
        "password": os.environ.get("WA_ACCOUNT_GITLAB_PASSWORD", "hello1234"),
        "output": ".auth/gitlab_state.json",
    },
}


def generate_state(
    url: str,
    login_path: str,
    username_field: str,
    password_field: str,
    submit_button: str,
    success_url: str,
    username: str,
    password: str,
    output: str,
    headless: bool = False,
) -> bool:
    """Open a browser, log in, and save storageState to a JSON file.

    Returns True on success, False on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright is not installed.")
        print("  Run: pip install playwright && playwright install chromium")
        return False

    login_url = url.rstrip("/") + login_path

    print(f"  Target URL : {url}")
    print(f"  Login page : {login_url}")
    print(f"  Username   : {username}")
    print(f"  Output     : {output}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            # Step 1: Navigate to login page
            print(f"[1/5] Navigating to {login_url} ...")
            page.goto(login_url, timeout=30000, wait_until="networkidle")
            print(f"      Current URL: {page.url}")

            # Step 2: Fill username
            print(f"[2/5] Filling username field '{username_field}' ...")
            page.fill(username_field, username)
            print("      OK")

            # Step 3: Fill password
            print(f"[3/5] Filling password field '{password_field}' ...")
            page.fill(password_field, password)
            print("      OK")

            # Step 4: Click submit
            print(f"[4/5] Clicking submit button '{submit_button}' ...")
            page.click(submit_button)
            time.sleep(2)  # Wait for navigation

            # Step 5: Verify login success
            print(f"[5/5] Verifying login...")
            current = page.url
            print(f"      Current URL: {current}")

            # Check if we reached the success URL or got redirected
            if success_url.rstrip("/") in current or "login" not in current.lower():
                print(f"      ✅ Login successful!")
            else:
                print(f"      ⚠️  May still be on login page. Check screenshot.")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

            # Save storage state
            context.storage_state(path=output)
            print(f"\n  ✅ Storage state saved to: {output}")
            print(f"     File size: {os.path.getsize(output)} bytes")
            print()
            print(f"  Now use it with:")
            print(f"     python run_webarena.py --storage-state {output} ...")

            browser.close()
            return True

        except Exception as e:
            print(f"\n  ❌ Error: {e}")
            # Take screenshot for debugging
            try:
                screenshot_path = output.replace(".json", "_debug.png")
                page.screenshot(path=screenshot_path)
                print(f"     Debug screenshot saved to: {screenshot_path}")
            except Exception:
                pass
            browser.close()
            return False


def main():
    ap = argparse.ArgumentParser(
        description="Generate Playwright storageState for WebArena sites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate state for shopping site with defaults
  python generate_auth_state.py

  # Generate state for all known sites
  python generate_auth_state.py --all-sites

  # Custom site
  python generate_auth_state.py --url "http://host:7770/login" \\
      --username "user@example.com" --password "pass123" \\
      --username-field "input[name='email']" \\
      --password-field "input[name='pwd']" \\
      --submit-button "button[type='submit']" \\
      --success-url "http://host:7770/" \\
      --output ".auth/custom_state.json"
        """,
    )
    ap.add_argument("--url", default=DEFAULT_URL,
                    help=f"Base URL of the WebArena site (default: from WA_SHOPPING env)")
    ap.add_argument("--login-path", default="/customer/account/login",
                    help="Path to the login page (default: /customer/account/login)")
    ap.add_argument("--username", default=DEFAULT_USERNAME,
                    help=f"Login username (default: from WA_ACCOUNT_SHOPPING_USERNAME env)")
    ap.add_argument("--password", default=DEFAULT_PASSWORD,
                    help=f"Login password (default: from WA_ACCOUNT_SHOPPING_PASSWORD env)")
    ap.add_argument("--username-field", default="input[name='login[username]']",
                    help="CSS selector for username input field")
    ap.add_argument("--password-field", default="input[name='login[password]']",
                    help="CSS selector for password input field")
    ap.add_argument("--submit-button", default="button[type='submit']",
                    help="CSS selector for submit button")
    ap.add_argument("--success-url", default=None,
                    help="Expected URL after successful login (for verification)")
    ap.add_argument("--output", default=DEFAULT_OUTPUT,
                    help="Output path for storageState JSON")
    ap.add_argument("--all-sites", action="store_true",
                    help="Generate storageState for all known WebArena sites")
    ap.add_argument("--headless", action="store_true", default=False,
                    help="Run browser in headless mode (default: visible for debugging)")
    args = ap.parse_args()

    if args.all_sites:
        print("=" * 60)
        print("  Generating storageState for ALL WebArena sites")
        print("=" * 60)
        all_ok = True
        for site_name, config in SITE_CONFIGS.items():
            print(f"\n{'='*60}")
            print(f"  Site: {site_name}")
            print(f"{'='*60}")
            ok = generate_state(
                url=config["url"],
                login_path=config["login_path"],
                username_field=config["username_field"],
                password_field=config["password_field"],
                submit_button=config["submit_button"],
                success_url=config["success_url"],
                username=config["username"],
                password=config["password"],
                output=config["output"],
                headless=args.headless,
            )
            if not ok:
                all_ok = False
        print(f"\n{'='*60}")
        if all_ok:
            print("  ✅ All sites generated successfully!")
        else:
            print("  ⚠️  Some sites failed. Check logs above.")
        print(f"{'='*60}")
        return

    success_url = args.success_url or args.url.rstrip("/") + "/"

    generate_state(
        url=args.url,
        login_path=args.login_path,
        username_field=args.username_field,
        password_field=args.password_field,
        submit_button=args.submit_button,
        success_url=success_url,
        username=args.username,
        password=args.password,
        output=args.output,
        headless=args.headless,
    )


if __name__ == "__main__":
    main()
