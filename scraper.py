"""
PitcherList scraper — fetches SP Streamers article and parses pitcher tables.
"""

import re
import time
import logging
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STREAMERS_INDEX_URL = "https://pitcherlist.com/category/fantasy/starting-pitchers/sp-streamers/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

# Tiers we care about (normalized to title case for display)
WANTED_TIERS = {"auto start", "probably start"}
TIER_DISPLAY = {
    "auto start": "Auto-Start",
    "probably start": "Probably Start",
}


def _get_with_retries(url: str, retries: int = 3, delay: float = 5.0) -> requests.Response:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def _is_today(time_ago_text: str, title_text: str, target_date: date) -> bool:
    """
    Determine if a PitcherList article was published on target_date.

    The index page shows relative time ("3 Hours Ago", "47 Minutes Ago") for
    the featured/most-recent article, and "M/D/YYYY" for older ones.
    """
    text = time_ago_text.strip()

    # Relative time indicators → article was posted today
    relative_markers = ("ago", "just now", "hour", "minute", "second")
    if any(m in text.lower() for m in relative_markers):
        return True

    # Absolute date: "4/3/2026"
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        m, d, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return date(y, m, d) == target_date

    # Fallback: look for today's date in the title ("4/4 & 4/5 & 4/6")
    today_slash = target_date.strftime("%-m/%-d")
    if today_slash in title_text:
        return True

    return False


def get_todays_article_url(target_date: Optional[date] = None) -> Optional[str]:
    """
    Scrapes the SP Streamers index and returns the URL of today's article,
    or None if it hasn't been posted yet.
    """
    if target_date is None:
        target_date = date.today()

    resp = _get_with_retries(STREAMERS_INDEX_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    # --- Featured (most-recent) article ---
    feature = soup.select_one(".feature.recent")
    if feature:
        time_ago_el = feature.select_one(".time-ago")
        title_el = feature.select_one("h2")
        link_el = feature.select_one("a[href]")

        time_ago = time_ago_el.get_text(strip=True) if time_ago_el else ""
        title = title_el.get_text(strip=True) if title_el else ""

        if link_el and _is_today(time_ago, title, target_date):
            return link_el["href"]

    # --- Below-fold article list ---
    for box in soup.select(".article-box-pl-stream"):
        time_ago_el = box.select_one(".time-ago")
        title_el = box.select_one("h2, h3")
        link_el = box.select_one("a[href]")

        time_ago = time_ago_el.get_text(strip=True) if time_ago_el else ""
        title = title_el.get_text(strip=True) if title_el else ""

        if link_el and _is_today(time_ago, title, target_date):
            return link_el["href"]

    return None


# ---------------------------------------------------------------------------
# Article parsing
# ---------------------------------------------------------------------------

def _parse_pitcher_table(table_el) -> list[dict]:
    """
    Parse a single pitcher ranking <table> into a list of dicts:
      {name, matchup, tier}

    The table structure (actual PitcherList format):
      Row 0:  ['Rank', 'Pitcher', 'Matchup', 'Rostership']   ← header
      Row N:  ['', 'Auto Start', '', '']                     ← tier header
      Row N+: ['1', 'Tyler Glasnow', '@ WSN', '94%']         ← pitcher
    """
    rows = []
    current_tier = None

    for tr in table_el.select("tr"):
        cells = tr.select("td, th")
        texts = [c.get_text(strip=True) for c in cells]

        if len(texts) < 2:
            continue

        # Header row (column labels)
        if texts[0].lower() in ("rank", "#") and texts[1].lower() == "pitcher":
            continue

        # Tier header row: first cell empty, second cell is tier name
        if texts[0] == "" and texts[1] != "":
            tier_key = texts[1].lower().strip()
            current_tier = TIER_DISPLAY.get(tier_key)  # None if not a wanted tier
            continue

        # Pitcher row: first cell is a rank number, second is pitcher name
        if current_tier is None:
            continue  # skip rows that are in an unwanted tier

        rank_cell = texts[0]
        if not rank_cell.isdigit():
            continue

        name = texts[1] if len(texts) > 1 else ""
        matchup = texts[2] if len(texts) > 2 else ""

        # Clean name: strip opener tags like "(Opener)"
        name = re.sub(r"\(Opener\)", "", name, flags=re.IGNORECASE).strip()
        # Remove duplicate Jr. suffixes (e.g. "Lance McCullers Jr.Jr." → "Lance McCullers Jr.")
        name = re.sub(r"(Jr\.|Sr\.|II|III|IV)\1+", r"\1", name).strip()

        if name:
            rows.append({"name": name, "matchup": matchup, "tier": current_tier})

    return rows


def fetch_and_parse_article(url: str, day_index: int = 2) -> list[dict]:
    """
    Fetches the article at `url` and returns pitcher dicts for the Nth day's table
    (1-indexed; default = 2 for tomorrow), filtered to Auto-Start and Probably Start tiers.

    Table layout on PitcherList:
      table[0]  — matchup quality grid (skip)
      table[1]  — Day 1 pitchers
      table[2]  — Day 2 pitchers
      ...

    So the target table index is day_index (because we skip table[0]).

    On parse failure, writes debug_article.html and returns [].
    """
    resp = _get_with_retries(url)
    soup = BeautifulSoup(resp.text, "lxml")

    tables = soup.select("table")

    # table[0] is the matchup quality grid; pitcher tables start at index 1
    target_table_idx = day_index  # day 1 → tables[1], day 2 → tables[2]

    if len(tables) <= target_table_idx:
        debug_path = "debug_article.html"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        logger.warning(
            "Expected at least %d tables but found %d. Raw HTML → %s",
            target_table_idx + 1,
            len(tables),
            debug_path,
        )
        return []

    pitchers = _parse_pitcher_table(tables[target_table_idx])

    if not pitchers:
        debug_path = "debug_article.html"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        logger.warning(
            "Parsed 0 pitchers from table %d. Raw HTML → %s",
            target_table_idx,
            debug_path,
        )

    return pitchers
