"""
Email notifications via Brevo (formerly Sendinblue).
"""

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SENT_DIR = Path(__file__).resolve().parent / ".sent"


def _was_sent_today(target_date: str) -> bool:
    """Check if an email was already sent for this date."""
    return (SENT_DIR / f"{target_date}.sent").exists()


def _mark_sent(target_date: str) -> None:
    """Record that an email was sent for this date."""
    SENT_DIR.mkdir(exist_ok=True)
    (SENT_DIR / f"{target_date}.sent").touch()


def send_sms(all_pitchers: list[dict], available: list[dict], target_date: str) -> bool:
    """
    Send an email with top-tier streamers and availability via Brevo.
    Returns True on success, False if skipped or failed.
    Silently skips if BREVO_API_KEY is not set.
    """
    api_key = os.getenv("BREVO_API_KEY")
    to_email = os.getenv("EMAIL_TO", "drucker.daniel@gmail.com")
    from_email = os.getenv("EMAIL_FROM", "drucker.daniel@gmail.com")

    if not api_key:
        logger.debug("BREVO_API_KEY not configured — skipping email")
        return False

    if _was_sent_today(target_date):
        print(f"Email already sent for {target_date} — skipping.")
        return False

    available_names = {p["name"] for p in available}

    rows = ""
    for i, p in enumerate(all_pitchers, 1):
        is_avail = p["name"] in available_names
        status = "✓ Available" if is_avail else "✗ Rostered"
        row_bg = "#f0fff4" if is_avail else "#ffffff"
        status_color = "#276749" if is_avail else "#718096"
        name_style = "font-weight:bold; color:#1a202c; background:#fefcbf; padding:1px 4px; border-radius:3px;"
        rows += (
            f"<tr style='background:{row_bg};'>"
            f"<td style='padding:6px 10px; color:#718096;'>{i}</td>"
            f"<td style='padding:6px 10px;'><span style='{name_style}'>{p['name']}</span></td>"
            f"<td style='padding:6px 10px; color:#4a5568;'>{p['tier']}</td>"
            f"<td style='padding:6px 10px; color:#4a5568;'>{p['matchup']}</td>"
            f"<td style='padding:6px 10px; font-weight:bold; color:{status_color};'>{status}</td>"
            f"</tr>"
        )

    html_body = f"""
<html><body style="font-family:Arial,sans-serif; font-size:14px; color:#1a202c; padding:20px;">
<h2 style="margin-bottom:16px;">SP Streamers — {target_date}</h2>
<table style="border-collapse:collapse; width:100%; max-width:600px;">
  <thead>
    <tr style="background:#2d3748; color:#ffffff;">
      <th style="padding:8px 10px; text-align:left;">#</th>
      <th style="padding:8px 10px; text-align:left;">Pitcher</th>
      <th style="padding:8px 10px; text-align:left;">Tier</th>
      <th style="padding:8px 10px; text-align:left;">Matchup</th>
      <th style="padding:8px 10px; text-align:left;">Status</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</body></html>
"""

    # Plain text fallback
    text_lines = [f"SP Streamers {target_date}:"]
    for i, p in enumerate(all_pitchers, 1):
        status = "AVAIL" if p["name"] in available_names else "rostered"
        text_lines.append(f"{i}. {p['name']} ({p['tier']}) {p['matchup']} — {status}")
    text_body = "\n".join(text_lines)

    payload = {
        "sender": {"name": "SP Streamers", "email": from_email},
        "to": [{"email": to_email}],
        "subject": f"SP Streamers {target_date}",
        "htmlContent": html_body,
        "textContent": text_body,
    }

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        _mark_sent(target_date)
        print(f"\n--- Email content ---\n{text_body}\n---")
        print(f"Email sent to {to_email}")
        return True
    except requests.HTTPError as e:
        logger.error("Failed to send email: %s — %s", e, resp.text)
        return False
