"""
Terminal display helpers using tabulate.
"""

from datetime import datetime
from tabulate import tabulate


def print_all_streamers(pitchers: list[dict]) -> None:
    """Print a clean table of all scraped pitchers (both tiers)."""
    if not pitchers:
        print("  (no pitchers found)")
        return

    rows = [[p["name"], p["matchup"], p["tier"]] for p in pitchers]
    print(tabulate(
        rows,
        headers=["Pitcher", "Matchup", "Tier"],
        tablefmt="fancy_grid",
        colalign=("left", "left", "left"),
    ))


def print_available_streamers(available: list[dict]) -> None:
    """Print a clean table of available pitchers with stats."""
    if not available:
        print("  (none of the top streamers are available in your league)")
        return

    rows = [
        [p["name"], p["tier"], p["matchup"], p["status"], p["ERA"], p["WHIP"], p["K/9"]]
        for p in available
    ]
    print(tabulate(
        rows,
        headers=["Pitcher", "Tier", "Matchup", "Avail.", "ERA", "WHIP", "K/9"],
        tablefmt="fancy_grid",
        colalign=("left", "left", "left", "left", "right", "right", "right"),
    ))


def save_results(pitchers: list[dict], available: list[dict], target_date: str) -> str:
    """Save full results to a timestamped file and return the filename."""
    filename = f"available_streamers_{target_date}.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"SP Streamers Report — generated {ts}",
        f"Target date: {target_date}",
        "",
        "=" * 60,
        "ALL SCRAPED STREAMERS (Auto-Start + Probably Start)",
        "=" * 60,
    ]

    if pitchers:
        rows = [[p["name"], p["matchup"], p["tier"]] for p in pitchers]
        lines.append(tabulate(rows, headers=["Pitcher", "Matchup", "Tier"], tablefmt="grid"))
    else:
        lines.append("  (none)")

    lines += [
        "",
        "=" * 60,
        "AVAILABLE IN YOUR LEAGUE",
        "=" * 60,
    ]

    if available:
        rows = [
            [p["name"], p["tier"], p["matchup"], p["status"], p["ERA"], p["WHIP"], p["K/9"]]
            for p in available
        ]
        lines.append(tabulate(
            rows,
            headers=["Pitcher", "Tier", "Matchup", "Avail.", "ERA", "WHIP", "K/9"],
            tablefmt="grid",
        ))
    else:
        lines.append("  (none available)")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return filename
