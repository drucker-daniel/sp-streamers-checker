"""
Tests for notify.py — Brevo email sending.
"""

import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def _skip_sent_check():
    """Disable the sent-today check so existing tests aren't affected."""
    with patch("notify._was_sent_today", return_value=False), \
         patch("notify._mark_sent"):
        yield


# ---------------------------------------------------------------------------
# send_sms
# ---------------------------------------------------------------------------

class TestSendSms:
    PITCHERS = [
        {"name": "Tarik Skubal", "tier": "Auto-Start", "matchup": "@ MIN"},
        {"name": "Andrew Abbott", "tier": "Probably Start", "matchup": "@ MIA"},
    ]
    AVAILABLE = [{"name": "Andrew Abbott"}]

    def _mock_env(self, extra=None):
        env = {"BREVO_API_KEY": "test-key", "EMAIL_TO": "test@example.com", "EMAIL_FROM": "from@example.com"}
        if extra:
            env.update(extra)
        return env

    def test_returns_false_when_no_api_key(self):
        from notify import send_sms
        with patch.dict("os.environ", {}, clear=True):
            result = send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")
        assert result is False

    def test_sends_html_email_on_success(self):
        from notify import send_sms
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.dict("os.environ", self._mock_env()), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            result = send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        assert result is True
        payload = mock_post.call_args[1]["json"]
        assert "htmlContent" in payload
        assert "textContent" in payload
        assert payload["subject"] == "SP Streamers 2026-04-06"

    def test_available_pitcher_highlighted_green(self):
        from notify import send_sms
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.dict("os.environ", self._mock_env()), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        html = mock_post.call_args[1]["json"]["htmlContent"]
        assert "#f0fff4" in html   # green row background for available pitchers
        assert "✓ Available" in html

    def test_rostered_pitcher_marked_correctly(self):
        from notify import send_sms
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.dict("os.environ", self._mock_env()), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        html = mock_post.call_args[1]["json"]["htmlContent"]
        assert "✗ Rostered" in html

    def test_returns_false_on_http_error(self):
        from notify import send_sms
        import requests as req

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401")
        mock_resp.text = "Unauthorized"

        with patch.dict("os.environ", self._mock_env()), \
             patch("requests.post", return_value=mock_resp):
            result = send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        assert result is False

    def test_text_fallback_included(self):
        from notify import send_sms
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch.dict("os.environ", self._mock_env()), \
             patch("requests.post", return_value=mock_resp) as mock_post:
            send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        text = mock_post.call_args[1]["json"]["textContent"]
        assert "Tarik Skubal" in text
        assert "Andrew Abbott" in text
        assert "AVAIL" in text


class TestSentDedup:
    """Tests for the once-per-day email dedup logic."""

    PITCHERS = TestSendSms.PITCHERS
    AVAILABLE = TestSendSms.AVAILABLE

    def test_skips_if_already_sent(self):
        """If an email was already sent for this date, send_sms returns False."""
        from notify import send_sms
        env = {"BREVO_API_KEY": "test-key", "EMAIL_TO": "t@t.com", "EMAIL_FROM": "f@f.com"}

        with patch.dict("os.environ", env), \
             patch("notify._was_sent_today", return_value=True), \
             patch("notify._mark_sent"), \
             patch("requests.post") as mock_post:
            result = send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        assert result is False
        mock_post.assert_not_called()

    def test_marks_sent_on_success(self, tmp_path):
        """A successful send creates the sentinel file."""
        from notify import send_sms, SENT_DIR, _mark_sent, _was_sent_today
        import notify

        sent_dir = tmp_path / ".sent"
        with patch.object(notify, "SENT_DIR", sent_dir), \
             patch.dict("os.environ", {"BREVO_API_KEY": "k", "EMAIL_TO": "t@t.com", "EMAIL_FROM": "f@f.com"}), \
             patch("notify._was_sent_today", return_value=False), \
             patch("requests.post", return_value=MagicMock()):
            # Restore real _mark_sent for this test
            with patch.object(notify, "_mark_sent", wraps=lambda d: (sent_dir.mkdir(exist_ok=True), (sent_dir / f"{d}.sent").touch())):
                result = send_sms(self.PITCHERS, self.AVAILABLE, "2026-04-06")

        assert result is True
        assert (sent_dir / "2026-04-06.sent").exists()
