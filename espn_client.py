"""
ESPN Fantasy Baseball client — wraps espn-api to check player availability.
"""

import logging
import os
import re
import unicodedata
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _load_espn_league():
    """Load and return the ESPN league object. Raises on auth/config failure."""
    try:
        from espn_api.baseball import League
    except ImportError:
        raise ImportError("espn-api is not installed. Run: pip install espn-api")

    league_id_str = os.getenv("LEAGUE_ID")
    year_str = os.getenv("YEAR")

    missing = [k for k, v in {"LEAGUE_ID": league_id_str, "YEAR": year_str}.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required .env variables: {', '.join(missing)}")

    try:
        league_id = int(league_id_str)
        year = int(year_str)
    except ValueError as e:
        raise EnvironmentError(f"LEAGUE_ID and YEAR must be integers: {e}")

    email = os.getenv("ESPN_EMAIL")
    password = os.getenv("ESPN_PASSWORD")
    if not email or not password:
        raise EnvironmentError("ESPN_EMAIL and ESPN_PASSWORD must be set in .env")

    try:
        from refresh_cookies import get_espn_cookies
        espn_s2, swid = get_espn_cookies(email, password)
    except Exception as e:
        raise RuntimeError(f"Failed to get ESPN cookies via login: {e}") from e

    try:
        league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        return league
    except Exception as e:
        raise RuntimeError(f"ESPN API failed after cookie refresh: {e}") from e


def _normalize_name(name: str) -> str:
    """Lowercase, remove diacritics, remove common suffixes for fuzzy matching."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def _names_match(scraped: str, espn: str) -> bool:
    """
    True if names match after normalization.
    Fuzzy fallback: same last name AND same first initial (handles diacritics/suffixes).
    """
    ns, ne = _normalize_name(scraped), _normalize_name(espn)
    if ns == ne:
        return True
    parts_s = ns.split()
    parts_e = ne.split()
    if len(parts_s) < 2 or len(parts_e) < 2:
        return False
    last_s, last_e = parts_s[-1], parts_e[-1]
    if last_s != last_e:
        return False
    first_s, first_e = parts_s[0], parts_e[0]
    if first_s != first_e:
        return False
    # If both names have the same number of tokens, they match.
    # If one has a middle name/initial that the other lacks, treat them as different
    # players (e.g. "Luis Castillo" vs "Luis F. Castillo" are two different people).
    if len(parts_s) != len(parts_e):
        return False
    return True


def _get_player_stats(player) -> dict:
    """
    Extract ERA, WHIP, K/9 from an ESPN player's season stats.

    ESPN stores season stats at scoring_period = 0 (full-season breakdown).
    The 'breakdown' dict is keyed by human-readable stat names from STATS_MAP.
    """
    stats = {}
    try:
        season = player.stats.get(0, {})
        breakdown = season.get("breakdown", {})
        if not breakdown:
            # Fall back to any period that has a breakdown
            for v in player.stats.values():
                if isinstance(v, dict) and v.get("breakdown"):
                    breakdown = v["breakdown"]
                    break

        era = breakdown.get("ERA")
        whip = breakdown.get("WHIP")
        k9 = breakdown.get("K/9")

        if era is not None:
            stats["ERA"] = f"{float(era):.2f}"
        if whip is not None:
            stats["WHIP"] = f"{float(whip):.2f}"
        if k9 is not None:
            stats["K/9"] = f"{float(k9):.1f}"
    except Exception:
        pass
    return stats


def check_availability(pitchers: list[dict], dry_run: bool = False) -> list[dict]:
    """
    Cross-reference `pitchers` (list of {name, matchup, tier}) against ESPN free agents.
    Returns only pitchers who are available, with availability and stat info added.

    In dry_run mode, skips the ESPN API call entirely.
    """
    if dry_run:
        logger.info("Dry-run mode: skipping ESPN API call")
        return [
            {**p, "status": "DRY-RUN", "ERA": "—", "WHIP": "—", "K/9": "—"}
            for p in pitchers
        ]

    league = _load_espn_league()

    # Build a set of rostered player names from all teams — this is the ground truth
    rostered: set[str] = set()
    try:
        for team in league.teams:
            for player in team.roster:
                rostered.add(_normalize_name(player.name))
    except Exception as e:
        logger.warning("Could not build roster set: %s", e)

    # Fetch candidate SP pool from ESPN's free-agent endpoint
    try:
        fa_candidates = league.free_agents(size=500, position="SP")
    except Exception as e:
        logger.warning("free_agents(position='SP') failed (%s); fetching all", e)
        try:
            fa_candidates = league.free_agents(size=500)
        except Exception as e2:
            logger.error("ESPN free_agents failed: %s", e2)
            return []

    # Keep only players genuinely not on any roster
    free_agents = [p for p in fa_candidates if _normalize_name(p.name) not in rostered]

    # Build lookup by normalized name
    fa_by_name: dict[str, object] = {_normalize_name(p.name): p for p in free_agents}

    results = []
    for pitcher in pitchers:
        pitcher_name = pitcher["name"]
        norm = _normalize_name(pitcher_name)

        espn_player = fa_by_name.get(norm)

        if espn_player is None:
            # Fuzzy match by last name / diacritic-insensitive
            for fa_norm, fa_player in fa_by_name.items():
                if _names_match(pitcher_name, fa_player.name):
                    espn_player = fa_player
                    break

        if espn_player is None:
            continue  # Not on waivers/FA — skip

        # Only surface free agents, not waiver-wire players
        acq = (espn_player.acquisitionType or "").upper()
        if acq != "FREEAGENT":
            continue
        status = "FA"

        stats = _get_player_stats(espn_player)

        results.append({
            "name": pitcher_name,
            "tier": pitcher["tier"],
            "matchup": pitcher["matchup"],
            "status": status,
            "ERA": stats.get("ERA", "—"),
            "WHIP": stats.get("WHIP", "—"),
            "K/9": stats.get("K/9", "—"),
        })

    return results
