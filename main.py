#!/usr/bin/env python3
"""
SP Streamers Availability Checker
Polls PitcherList for today's SP Streamers article, parses the target day's
pitcher tables, and cross-references against your ESPN Fantasy Baseball league.
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

from scraper import get_todays_article_url, fetch_and_parse_article
from espn_client import check_availability
from display import print_all_streamers, print_available_streamers, save_results
from notify import send_sms

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_ARTICLE_INTERVAL = 5 * 60   # seconds between article polls
RECHECK_ESPN_INTERVAL = 30 * 60  # seconds between ESPN availability rechecks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%I:%M %p")


def _today_str() -> str:
    return date.today().isoformat()


def _wait_for_article(target_date: date) -> str:
    """Block until today's PitcherList article is live. Returns its URL."""
    while True:
        url = get_todays_article_url(target_date)
        if url:
            print(f"\n[{_now_str()}] Found today's article: {url}")
            return url
        print(
            f"[{_now_str()}] No new article yet for {target_date}. "
            f"Checking again in 5 minutes..."
        )
        time.sleep(POLL_ARTICLE_INTERVAL)


def _run_full_check(article_url: str, day_index: int, dry_run: bool, target_date: str, notify: bool = False):
    """Scrape article, check ESPN availability, display & save results."""
    print(f"\n{'=' * 60}")
    print(f"Fetching article: {article_url}")
    print(f"Parsing day {day_index} table...")
    print(f"{'=' * 60}\n")

    pitchers = fetch_and_parse_article(article_url, day_index=day_index)

    if not pitchers:
        print("[WARNING] No pitchers parsed from the article.")
        print("Check debug_article.html if it was created.")
        return

    day_label = "Today" if day_index == 1 else "Tomorrow"
    print(f"{day_label}'s Streamers (Auto-Start + Probably Start)\n")
    print_all_streamers(pitchers)

    if dry_run:
        print("\n[Dry-run mode] Skipping ESPN availability check.\n")
        return

    print(f"\n{'=' * 60}")
    print("Checking ESPN availability...")
    print(f"{'=' * 60}\n")

    available = check_availability(pitchers, dry_run=dry_run)

    print(f"Available in your ESPN league ({len(available)} found):\n")
    print_available_streamers(available)

    filename = save_results(pitchers, available, target_date)
    print(f"\nResults saved to: {filename}\n")

    if notify:
        send_sms(pitchers, available, target_date)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Check SP Streamers availability in your ESPN Fantasy Baseball league."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scraped pitcher names without hitting the ESPN API.",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=2,
        metavar="N",
        help="Which day's table to target (1 = today, 2 = tomorrow [default]).",
    )
    parser.add_argument(
        "--date",
        dest="target_date_str",
        default=None,
        metavar="YYYY-MM-DD",
        help="Override the article date to look for (default: today).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running and re-check ESPN availability every 30 minutes.",
    )
    args = parser.parse_args()

    # Validate day
    if args.day < 1:
        parser.error("--day must be >= 1")

    # Resolve target date
    if args.target_date_str:
        try:
            target_date = date.fromisoformat(args.target_date_str)
        except ValueError:
            parser.error(f"Invalid --date format: {args.target_date_str!r}. Use YYYY-MM-DD.")
    else:
        target_date = date.today()

    target_date_str = target_date.isoformat()

    print(f"\nSP Streamers Checker — {target_date_str}")
    print(f"Targeting day {args.day} table | Dry-run: {args.dry_run}\n")

    # --- Step 1: Wait for today's article ---
    print(f"[{_now_str()}] Checking for today's PitcherList SP Streamers article...")
    article_url = get_todays_article_url(target_date)

    if article_url:
        print(f"[{_now_str()}] Article already live: {article_url}")
    else:
        article_url = _wait_for_article(target_date)

    # --- Step 2: Initial scrape + availability check (send SMS on first run) ---
    _run_full_check(article_url, args.day, args.dry_run, target_date_str, notify=True)

    if args.dry_run or not args.loop:
        return

    # --- Step 3: Re-check ESPN availability every 30 minutes ---
    print(f"Monitoring for roster changes every 30 minutes. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(RECHECK_ESPN_INTERVAL)
            print(f"\n[{_now_str()}] Re-checking ESPN availability...")
            _run_full_check(article_url, args.day, args.dry_run, target_date_str)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
