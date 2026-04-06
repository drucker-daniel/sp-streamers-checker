#!/usr/bin/env python3
"""
Automates ESPN login to extract fresh ESPN_S2 and SWID cookies,
then writes them back to the .env file.

Usage:
    python3 refresh_cookies.py

Requires ESPN_EMAIL and ESPN_PASSWORD in .env.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ENV_FILE = Path(__file__).parent / ".env"


def _update_env_file(espn_s2: str, swid: str) -> None:
    """Write ESPN_S2 and SWID into the .env file, creating it if needed."""
    content = ENV_FILE.read_text() if ENV_FILE.exists() else ""

    def replace_or_append(text: str, key: str, value: str) -> str:
        pattern = rf"^{key}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            return re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text + f"\n{replacement}"

    content = replace_or_append(content, "ESPN_S2", espn_s2)
    content = replace_or_append(content, "SWID", swid)
    ENV_FILE.write_text(content)


def get_espn_cookies(email: str, password: str) -> tuple[str, str]:
    """
    Headless-browser login to ESPN; returns (espn_s2, swid).
    Raises RuntimeError if login fails or cookies aren't found.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise ImportError(
            "playwright is not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    debug = os.getenv("ESPN_DEBUG", "").lower() in ("1", "true", "yes")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            league_id = os.getenv("LEAGUE_ID", "")
            print(f"Navigating to fantasy league page (leagueId={league_id})...")
            page.goto(
                f"https://fantasy.espn.com/baseball/league?leagueId={league_id}",
                wait_until="networkidle", timeout=30000,
            )

            # ESPN redirects to login — find the login iframe
            frame = None
            for _ in range(20):
                for f in page.frames:
                    if "disneyid" in f.url or "registerdisney" in f.url:
                        if f.locator("input[type='email']").count() > 0:
                            frame = f
                            break
                if frame:
                    break
                page.wait_for_timeout(500)

            if frame is None:
                frame = page

            print("Entering email...")
            frame.wait_for_selector("input[type='email']", timeout=15000)
            frame.fill("input[type='email']", email)
            page.wait_for_timeout(1000)

            # Two-step flow: click Continue if password not yet visible
            if frame.locator("input[type='password']").count() == 0:
                continue_btn = frame.locator("button:has-text('Continue'), button:has-text('Next'), button:has-text('Log In')")
                if continue_btn.count() > 0:
                    continue_btn.first.click()
                    page.wait_for_timeout(2000)

            print("Entering password...")
            frame.wait_for_selector("input[type='password']", timeout=30000)
            frame.fill("input[type='password']", password)

            frame.locator("button:has-text('Log In'), button:has-text('Sign In')").first.click()
            print("Submitted login form.")

            # Wait up to 90s for login + any OTP/2FA to complete
            print("Waiting for login to complete (up to 90s for OTP if needed)...")
            try:
                page.wait_for_url(re.compile(r"fantasy\.espn\.com"), timeout=90000)
            except PWTimeout:
                pass

            page.wait_for_timeout(3000)
            print(f"Current URL: {page.url}")

        except PWTimeout as e:
            browser.close()
            raise RuntimeError(f"Timed out during ESPN login: {e}")

        # Extract cookies
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        if debug:
            print("All ESPN/SWID cookies found:")
            for k, v in sorted(cookies.items()):
                if any(x in k.lower() for x in ["espn", "swid", "s2"]):
                    print(f"  {k}: {v[:80]}")
        browser.close()

    espn_s2 = cookies.get("espn_s2") or cookies.get("ESPN_S2")
    swid = cookies.get("SWID") or cookies.get("swid")

    if not espn_s2 or not swid:
        found = [k for k in cookies if "espn" in k.lower() or "swid" in k.lower()]
        raise RuntimeError(
            f"Login succeeded but ESPN_S2/SWID not found in cookies.\n"
            f"ESPN-related cookies found: {found}\n"
            "Your account may require 2FA or a CAPTCHA — try logging in manually."
        )

    return espn_s2, swid


def main():
    email = os.getenv("ESPN_EMAIL")
    password = os.getenv("ESPN_PASSWORD")

    if not email or not password:
        print(
            "ERROR: ESPN_EMAIL and ESPN_PASSWORD must be set in your .env file.\n"
            "Add them and re-run."
        )
        sys.exit(1)

    try:
        espn_s2, swid = get_espn_cookies(email, password)
    except (RuntimeError, ImportError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"ESPN_S2: {espn_s2[:20]}...")
    print(f"SWID:    {swid}")

    _update_env_file(espn_s2, swid)
    print(f"\nCookies written to {ENV_FILE}")


if __name__ == "__main__":
    main()
