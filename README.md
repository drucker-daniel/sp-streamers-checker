# SP Streamers Checker

Checks [PitcherList's daily SP Streamers article](https://pitcherlist.com/category/fantasy/starting-pitchers/sp-streamers/) and cross-references the top-ranked pitchers against your ESPN Fantasy Baseball league to surface who's actually available to pick up.

Sends an HTML email via Brevo with the full ranked list, highlighting available pitchers in green.

---

## How It Works

```
PitcherList article  →  scraper.py  →  espn_client.py  →  notify.py
     (HTML)               (parse)        (availability)     (email)
```

1. **`scraper.py`** — Fetches the SP Streamers index page and finds today's article. Parses the target day's pitcher table, keeping only `Auto-Start` and `Probably Start` tier pitchers.

2. **`espn_client.py`** — Logs into ESPN via headless browser (`refresh_cookies.py`) to get fresh auth cookies, then uses the `espn-api` library to load your league. Builds a set of all rostered players and fetches the free-agent SP pool. Cross-references the two lists to find who's available.

3. **`notify.py`** — Sends an HTML email via Brevo's API with the full ranked list as a table. Available pitchers get a green row; rostered pitchers are grey. Pitcher names are highlighted in yellow.

4. **`display.py`** — Renders the same results as a formatted table in the terminal and saves a `.txt` report file.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure `.env`

Copy `.env.example` to `.env` and fill in your values:

```
ESPN_EMAIL=your_espn_email@example.com
ESPN_PASSWORD=your_espn_password
LEAGUE_ID=194150          # from your ESPN league URL
YEAR=2026

BREVO_API_KEY=your_key    # from app.brevo.com → Settings → API Keys
EMAIL_TO=you@example.com
EMAIL_FROM=you@example.com
```

---

## Usage

### Run once (default: tomorrow's pitchers)
```bash
python3 main.py
```

### Run for today's pitchers
```bash
python3 main.py --day 1
```

### Dry run (scrape only, skip ESPN)
```bash
python3 main.py --dry-run
```

### Re-check ESPN every 30 minutes
```bash
python3 main.py --loop
```

### Check a specific date's article
```bash
python3 main.py --date 2026-04-07
```

---

## File Overview

| File | Purpose |
|---|---|
| `main.py` | Entry point — orchestrates scraping, ESPN check, and email |
| `scraper.py` | Fetches and parses the PitcherList article |
| `espn_client.py` | Checks pitcher availability against your ESPN league |
| `refresh_cookies.py` | Headless ESPN login to extract auth cookies |
| `notify.py` | Sends HTML email via Brevo |
| `display.py` | Terminal table display and `.txt` file output |
| `tests/` | Unit tests (42 tests, no network/ESPN required) |

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

Tests cover:
- Article date detection (relative and absolute timestamps)
- Pitcher table parsing (tiers, name cleaning, edge cases)
- ESPN name normalization and fuzzy matching (diacritics, Jr. suffixes)
- Availability filtering (rostered vs. FA vs. waivers)
- Email generation (HTML structure, status labels, error handling)

All tests use mocks — no network calls or ESPN credentials required.