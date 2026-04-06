"""
Tests for scraper.py — PitcherList article detection and pitcher table parsing.
"""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from scraper import _is_today, _parse_pitcher_table, fetch_and_parse_article


# ---------------------------------------------------------------------------
# _is_today
# ---------------------------------------------------------------------------

class TestIsToday:
    def test_relative_hours_ago(self):
        assert _is_today("3 Hours Ago", "", date(2026, 4, 6))

    def test_relative_minutes_ago(self):
        assert _is_today("47 Minutes Ago", "", date(2026, 4, 6))

    def test_just_now(self):
        assert _is_today("Just Now", "", date(2026, 4, 6))

    def test_absolute_date_match(self):
        assert _is_today("4/6/2026", "", date(2026, 4, 6))

    def test_absolute_date_no_match(self):
        assert not _is_today("4/5/2026", "", date(2026, 4, 6))

    def test_title_fallback_match(self):
        assert _is_today("", "SP Streamers 4/6 & 4/7", date(2026, 4, 6))

    def test_title_fallback_no_match(self):
        assert not _is_today("", "SP Streamers 4/5 & 4/6", date(2026, 4, 7))

    def test_empty_text_no_match(self):
        assert not _is_today("", "", date(2026, 4, 6))


# ---------------------------------------------------------------------------
# _parse_pitcher_table
# ---------------------------------------------------------------------------

def _make_table_html(rows_html: str) -> "BeautifulSoup element":
    """Helper: wrap row HTML in a <table> and return the element."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(f"<table>{rows_html}</table>", "lxml")
    return soup.select_one("table")


class TestParsePitcherTable:
    def _table(self, rows_html):
        return _make_table_html(rows_html)

    def test_parses_auto_start_pitchers(self):
        html = """
        <tr><th>Rank</th><th>Pitcher</th><th>Matchup</th><th>Rostership</th></tr>
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Tarik Skubal</td><td>@ MIN</td><td>99%</td></tr>
        <tr><td>2</td><td>Paul Skenes</td><td>vs. SDP</td><td>98%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert len(result) == 2
        assert result[0] == {"name": "Tarik Skubal", "matchup": "@ MIN", "tier": "Auto-Start"}
        assert result[1] == {"name": "Paul Skenes", "matchup": "vs. SDP", "tier": "Auto-Start"}

    def test_parses_probably_start_pitchers(self):
        html = """
        <tr><th>Rank</th><th>Pitcher</th><th>Matchup</th><th>Rostership</th></tr>
        <tr><td></td><td>Probably Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Andrew Abbott</td><td>@ MIA</td><td>45%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert len(result) == 1
        assert result[0]["tier"] == "Probably Start"

    def test_skips_unwanted_tiers(self):
        html = """
        <tr><th>Rank</th><th>Pitcher</th><th>Matchup</th><th>Rostership</th></tr>
        <tr><td></td><td>Avoid</td><td></td><td></td></tr>
        <tr><td>1</td><td>Bad Pitcher</td><td>vs. NYY</td><td>10%</td></tr>
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>2</td><td>Good Pitcher</td><td>@ BOS</td><td>90%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert len(result) == 1
        assert result[0]["name"] == "Good Pitcher"

    def test_strips_opener_tag(self):
        html = """
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Some Pitcher(Opener)</td><td>@ TEX</td><td>20%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert result[0]["name"] == "Some Pitcher"

    def test_deduplicates_jr_suffix(self):
        html = """
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Lance McCullers Jr.Jr.</td><td>vs. SEA</td><td>50%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert result[0]["name"] == "Lance McCullers Jr."

    def test_empty_table_returns_empty_list(self):
        result = _parse_pitcher_table(self._table(""))
        assert result == []

    def test_skips_rows_before_any_tier(self):
        html = """
        <tr><td>1</td><td>Orphan Pitcher</td><td>@ LAD</td><td>80%</td></tr>
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>2</td><td>Good Pitcher</td><td>@ BOS</td><td>90%</td></tr>
        """
        result = _parse_pitcher_table(self._table(html))
        assert len(result) == 1
        assert result[0]["name"] == "Good Pitcher"


# ---------------------------------------------------------------------------
# fetch_and_parse_article
# ---------------------------------------------------------------------------

class TestFetchAndParseArticle:
    def _mock_response(self, html: str):
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        return resp

    def _full_page(self, *tables_html):
        """Wrap multiple table HTML strings into a full page (table[0] is skipped)."""
        tables = "".join(f"<table>{t}</table>" for t in tables_html)
        return f"<html><body>{tables}</body></html>"

    def test_returns_pitchers_for_day2(self):
        day1 = """
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Day1 Pitcher</td><td>@ LAD</td><td>99%</td></tr>
        """
        day2 = """
        <tr><td></td><td>Auto Start</td><td></td><td></td></tr>
        <tr><td>1</td><td>Day2 Pitcher</td><td>vs. BOS</td><td>99%</td></tr>
        """
        html = self._full_page("<tr><td>grid</td></tr>", day1, day2)

        with patch("scraper._get_with_retries", return_value=self._mock_response(html)):
            result = fetch_and_parse_article("http://fake.url", day_index=2)

        assert len(result) == 1
        assert result[0]["name"] == "Day2 Pitcher"

    def test_returns_empty_list_when_table_missing(self, tmp_path, monkeypatch):
        html = "<html><body><table><tr><td>only one</td></tr></table></body></html>"
        monkeypatch.chdir(tmp_path)

        with patch("scraper._get_with_retries", return_value=self._mock_response(html)):
            result = fetch_and_parse_article("http://fake.url", day_index=2)

        assert result == []
        assert (tmp_path / "debug_article.html").exists()
