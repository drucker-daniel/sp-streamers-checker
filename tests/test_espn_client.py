"""
Tests for espn_client.py — name normalization, fuzzy matching, and availability check.
"""

import pytest
from unittest.mock import patch, MagicMock

from espn_client import _normalize_name, _names_match, check_availability


# ---------------------------------------------------------------------------
# _normalize_name
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_lowercases(self):
        assert _normalize_name("Tarik Skubal") == "tarik skubal"

    def test_strips_diacritics(self):
        assert _normalize_name("Cristopher Sánchez") == "cristopher sanchez"

    def test_strips_jr_suffix(self):
        assert _normalize_name("Lance McCullers Jr.") == "lance mccullers"

    def test_strips_sr_suffix(self):
        assert _normalize_name("John Smith Sr.") == "john smith"

    def test_strips_roman_numeral_suffix(self):
        assert _normalize_name("Ken Griffey Jr") == "ken griffey"

    def test_collapses_extra_spaces(self):
        assert _normalize_name("  Paul   Skenes  ") == "paul skenes"


# ---------------------------------------------------------------------------
# _names_match
# ---------------------------------------------------------------------------

class TestNamesMatch:
    def test_exact_match(self):
        assert _names_match("Tarik Skubal", "Tarik Skubal")

    def test_diacritic_insensitive(self):
        assert _names_match("Cristopher Sánchez", "Cristopher Sanchez")

    def test_jr_suffix_ignored(self):
        assert _names_match("Lance McCullers Jr.", "Lance McCullers")

    def test_different_last_name_no_match(self):
        assert not _names_match("Paul Skenes", "Paul Smith")

    def test_different_first_name_no_match(self):
        assert not _names_match("Luis Castillo", "Ramon Castillo")

    def test_middle_name_disambiguation(self):
        # "Luis Castillo" and "Luis F. Castillo" are different players
        assert not _names_match("Luis Castillo", "Luis F. Castillo")

    def test_single_token_no_match(self):
        assert not _names_match("Skubal", "Tarik Skubal")


# ---------------------------------------------------------------------------
# check_availability
# ---------------------------------------------------------------------------

class TestCheckAvailability:
    def test_dry_run_returns_all_pitchers(self):
        pitchers = [
            {"name": "Tarik Skubal", "matchup": "@ MIN", "tier": "Auto-Start"},
            {"name": "Paul Skenes", "matchup": "vs. SDP", "tier": "Auto-Start"},
        ]
        result = check_availability(pitchers, dry_run=True)
        assert len(result) == 2
        assert all(p["status"] == "DRY-RUN" for p in result)

    def test_dry_run_adds_stat_placeholders(self):
        pitchers = [{"name": "X", "matchup": "@ Y", "tier": "Auto-Start"}]
        result = check_availability(pitchers, dry_run=True)
        assert result[0]["ERA"] == "—"
        assert result[0]["WHIP"] == "—"
        assert result[0]["K/9"] == "—"

    def _make_espn_player(self, name, acquisition="FREEAGENT", stats=None):
        player = MagicMock()
        player.name = name
        player.acquisitionType = acquisition
        player.stats = stats or {}
        return player

    def _make_league(self, roster_names, fa_names):
        league = MagicMock()

        team = MagicMock()
        team.roster = [self._make_espn_player(n, "WAIVERS") for n in roster_names]
        league.teams = [team]

        fa = [self._make_espn_player(n, "FREEAGENT") for n in fa_names]
        league.free_agents.return_value = fa

        return league

    def test_returns_available_pitcher(self):
        pitchers = [{"name": "Andrew Abbott", "matchup": "@ MIA", "tier": "Probably Start"}]
        league = self._make_league(roster_names=[], fa_names=["Andrew Abbott"])

        with patch("espn_client._load_espn_league", return_value=league):
            result = check_availability(pitchers)

        assert len(result) == 1
        assert result[0]["name"] == "Andrew Abbott"
        assert result[0]["status"] == "FA"

    def test_excludes_rostered_pitcher(self):
        pitchers = [{"name": "Tarik Skubal", "matchup": "@ MIN", "tier": "Auto-Start"}]
        league = self._make_league(roster_names=["Tarik Skubal"], fa_names=[])

        with patch("espn_client._load_espn_league", return_value=league):
            result = check_availability(pitchers)

        assert result == []

    def test_excludes_waiver_wire_player(self):
        pitchers = [{"name": "Drew Rasmussen", "matchup": "vs. CHC", "tier": "Probably Start"}]
        league = self._make_league(roster_names=[], fa_names=[])

        # Player is on waivers (not FREEAGENT)
        waiver_player = self._make_espn_player("Drew Rasmussen", acquisition="WAIVERS")
        league.free_agents.return_value = [waiver_player]

        with patch("espn_client._load_espn_league", return_value=league):
            result = check_availability(pitchers)

        assert result == []

    def test_fuzzy_match_diacritics(self):
        pitchers = [{"name": "Cristopher Sánchez", "matchup": "@ SFG", "tier": "Auto-Start"}]
        league = self._make_league(roster_names=[], fa_names=["Cristopher Sanchez"])

        with patch("espn_client._load_espn_league", return_value=league):
            result = check_availability(pitchers)

        assert len(result) == 1
        assert result[0]["name"] == "Cristopher Sánchez"
