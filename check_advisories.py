#!/usr/bin/env python3
"""
Travel Advisory Monitor - runs via GitHub Actions (free)
Checks U.S. State Department travel advisories and sends Telegram notifications.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# Configuration from environment / GitHub Secrets
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Countries to monitor (comma-separated in env, or empty for all)
# Example: "Russia,Ukraine,Israel,China,Belarus"
MONITORED_COUNTRIES = [c.strip() for c in os.getenv("MONITORED_COUNTRIES", "").split(",") if c.strip()]

TRAVEL_URL = "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"
STATE_FILE = Path(__file__).parent / "state.json"

LEVEL_EMOJIS = {"1": "🟢", "2": "🟡", "3": "🟠", "4": "🔴"}


def fetch_advisories() -> dict[str, dict]:
    """Fetch current travel advisories from travel.state.gov"""
    advisories = {}

    response = httpx.get(TRAVEL_URL, follow_redirects=True, timeout=30.0)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find advisory table
    table = soup.find("table", class_="table-data") or soup.find("table")
    if not table:
        print("ERROR: Could not find advisory table")
        return advisories

    for row in table.find_all("tr")[1:]:  # Skip header
        cells = row.find_all("td")
        if len(cells) >= 2:
            # Country name
            country_cell = cells[0]
            link = country_cell.find("a")
            country = link.get_text(strip=True) if link else country_cell.get_text(strip=True)

            # Advisory level
            level_text = cells[1].get_text(strip=True)
            level = "".join(c for c in level_text if c.isdigit())[:1] or "0"

            # Date (if exists)
            date = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            advisories[country] = {
                "level": level,
                "text": level_text,
                "date": date
            }

    print(f"Fetched {len(advisories)} advisories")
    return advisories


def load_state() -> dict:
    """Load previous state from file"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(data: dict) -> None:
    """Save state to file"""
    STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def should_monitor(country: str) -> bool:
    """Check if country should be monitored"""
    if not MONITORED_COUNTRIES:
        return True
    return any(m.lower() in country.lower() for m in MONITORED_COUNTRIES)


def find_changes(old: dict, new: dict) -> list[dict]:
    """Find changes between old and new advisories"""
    changes = []

    for country, data in new.items():
        if not should_monitor(country):
            continue

        old_data = old.get(country, {})

        if not old_data:
            changes.append({
                "type": "new",
                "country": country,
                "level": data["level"],
                "text": data["text"]
            })
        elif data["level"] != old_data.get("level"):
            changes.append({
                "type": "changed",
                "country": country,
                "old_level": old_data["level"],
                "new_level": data["level"],
                "text": data["text"]
            })

    # Check removed
    for country in old:
        if should_monitor(country) and country not in new:
            changes.append({
                "type": "removed",
                "country": country,
                "old_level": old[country]["level"]
            })

    return changes


def format_message(changes: list[dict]) -> str:
    """Format changes for Telegram"""
    lines = ["🚨 <b>Travel Advisory Changes</b>\n"]

    for c in changes:
        country = c["country"]

        if c["type"] == "changed":
            old, new = c["old_level"], c["new_level"]
            direction = "⬆️" if int(new) > int(old) else "⬇️"
            lines.append(
                f"{direction} <b>{country}</b>\n"
                f"   {LEVEL_EMOJIS.get(old, '⚪')} Level {old} → "
                f"{LEVEL_EMOJIS.get(new, '⚪')} Level {new}\n"
            )

        elif c["type"] == "new":
            lvl = c["level"]
            lines.append(
                f"🆕 <b>{country}</b>\n"
                f"   {LEVEL_EMOJIS.get(lvl, '⚪')} Level {lvl}\n"
            )

        elif c["type"] == "removed":
            lines.append(f"❌ <b>{country}</b> - removed\n")

    lines.append(f"<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>")
    return "\n".join(lines)


def send_telegram(message: str) -> None:
    """Send message via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram credentials not set")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = httpx.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    })

    if response.status_code == 200:
        print("Telegram message sent")
    else:
        print(f"Telegram error: {response.text}")


def main():
    print(f"Checking advisories at {datetime.utcnow().isoformat()}")

    if MONITORED_COUNTRIES:
        print(f"Monitoring: {', '.join(MONITORED_COUNTRIES)}")
    else:
        print("Monitoring: ALL countries")

    # Fetch current data
    current = fetch_advisories()
    if not current:
        print("Failed to fetch advisories")
        sys.exit(1)

    # Load previous state
    previous = load_state()

    if previous:
        changes = find_changes(previous, current)
        if changes:
            print(f"Found {len(changes)} changes!")
            message = format_message(changes)
            send_telegram(message)
        else:
            print("No changes detected")
    else:
        print("First run - initializing state")
        # Send initial status for monitored countries
        if MONITORED_COUNTRIES:
            lines = ["📋 <b>Initial Advisory Status</b>\n"]
            for country, data in sorted(current.items()):
                if should_monitor(country):
                    emoji = LEVEL_EMOJIS.get(data["level"], "⚪")
                    lines.append(f"{emoji} <b>{country}</b>: Level {data['level']}")
            lines.append(f"\n<i>Bot started {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>")
            send_telegram("\n".join(lines))

    # Save current state
    save_state(current)
    print("Done")


if __name__ == "__main__":
    main()
