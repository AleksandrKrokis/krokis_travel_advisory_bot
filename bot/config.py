"""Configuration: geography, tiers, timings."""

import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Tallinn")

# Signal tiers
WATCH, PREPARE, LEAVE = 1, 2, 3

LEVELS = {
    0: ("🟢", "СПОКОЙНО"),
    1: ("🟡", "НАБЛЮДАТЬ"),
    2: ("🟠", "ГОТОВИТЬСЯ"),
    3: ("🔴", "УЕЗЖАТЬ"),
}

LEVEL_ADVICE = {
    0: "Особых действий не требуется.",
    1: "Следить внимательнее. Проверить сроки паспортов, держать запас наличных.",
    2: "Подготовиться к отъезду: документы, наличные, полный бак, план маршрута "
       "и жилья, билет на паром или самолёт с возможностью возврата.",
    3: "Уезжать сейчас, пока работают паромы и авиасообщение. "
       "Приоритет — паром Таллинн → Стокгольм или рейс на запад.",
}

# Geography. "home" signals weigh one tier more than neighbour signals.
HOME = {"name": "Estonia", "ru": "Эстония", "iso2": "EE", "fcdo": "estonia"}
NEIGHBORS = [
    {"name": "Latvia", "ru": "Латвия", "iso2": "LV", "fcdo": "latvia"},
    {"name": "Lithuania", "ru": "Литва", "iso2": "LT", "fcdo": "lithuania"},
    {"name": "Finland", "ru": "Финляндия", "iso2": "FI", "fcdo": "finland"},
    {"name": "Poland", "ru": "Польша", "iso2": "PL", "fcdo": "poland"},
]
COUNTRIES = [HOME] + NEIGHBORS

# A lower composite level is applied only after it held this long (anti-flapping)
DOWNGRADE_AFTER_HOURS = 72
# Event signals (news, embassy alerts) stay active this long
EVENT_TTL_DAYS = 7
# Report a source to admin when it has been failing this long
SOURCE_FAIL_ALERT_HOURS = 12
# Digest is sent on/after this UTC hour (Mondays; daily when level >= WATCH)
DIGEST_HOUR_UTC = 6

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Channel / subscribers. Comma-separated.
TELEGRAM_CHAT_IDS = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
# Technical messages (source failures). Optional, never the channel.
TELEGRAM_ADMIN_CHAT_IDS = [c.strip() for c in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",") if c.strip()]

DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
