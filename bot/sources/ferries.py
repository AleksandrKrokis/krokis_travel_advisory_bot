"""Tallink one-way availability and prices out of Tallinn.

Sold-out ferries mean others are already leaving. Storms and holidays also
fill or cancel sailings, so this is only WATCH (PREPARE when both routes are
affected) and must persist for two consecutive checks.
"""

import statistics
from datetime import datetime, timedelta

from .. import http
from ..config import PREPARE, TZ, WATCH
from ..signals import Signal, SourceResult

ROUTES = [("tal", "hel", "Таллинн → Хельсинки"), ("tal", "sto", "Таллинн → Стокгольм")]
HISTORY = 40  # checks (~5 days at 3h interval)


def fetch(frm: str, to: str, now: datetime) -> list[dict]:
    d = http.get("https://booking.tallink.com/api/timetables", params={
        "locale": "en", "country": "EE", "from": frm, "to": to, "oneWay": "true",
        "dateFrom": now.date().isoformat(), "dateTo": (now + timedelta(days=7)).date().isoformat(),
        "voyageType": "SHUTTLE", "includeOvernight": "true", "searchFutureSails": "false",
    }).json()
    sails = []
    for day in (d.get("trips") or {}).values():
        for s in day.get("outwards") or []:
            dep = datetime.fromisoformat(s["departureIsoDate"])
            sails.append({"dep": dep, "room": bool(s.get("hasRoom")) and not s.get("isDisabled"),
                          "price": float(s["personPrice"]) if s.get("personPrice") else None})
    return sails


def route_metrics(sails: list[dict], now: datetime) -> dict:
    local_now = now.astimezone(TZ).replace(tzinfo=None)  # Tallink times are local
    upcoming = sorted((s for s in sails if s["dep"] > local_now), key=lambda s: s["dep"])
    soon = [s for s in upcoming if s["dep"] <= local_now + timedelta(hours=48)] or upcoming[:2]
    prices = [s["price"] for s in upcoming[:6] if s["price"]]
    return {
        "n": len(soon),
        "avail": sum(s["room"] for s in soon) / len(soon) if soon else 0.0,
        "price": min(prices) if prices else None,
    }


class TallinkFerries:
    name = "ferries"
    title = "Tallink: паромы"
    interval_hours = 3

    def collect(self, st: dict, now: datetime) -> SourceResult:
        res = SourceResult()
        problems = []
        for frm, to, label in ROUTES:
            key = f"{frm}-{to}"
            m = route_metrics(fetch(frm, to, now), now)
            hist = st.setdefault(key, [])
            prices = [h["price"] for h in hist if h.get("price")]
            avails = [h["avail"] for h in hist]
            reasons = []
            if m["n"] == 0:
                reasons.append("нет рейсов в продаже")
            elif len(avails) >= 8 and statistics.median(avails) >= 0.7 and m["avail"] < 0.3:
                reasons.append(f"мест почти нет: доступно {m['avail']:.0%} рейсов на ближайшие 48 ч")
            if m["price"] and len(prices) >= 8 and m["price"] > 2.5 * statistics.median(prices):
                reasons.append(f"цена {m['price']:.0f} € при обычной ~{statistics.median(prices):.0f} €")

            streak_key = f"{key}:streak"
            st[streak_key] = st.get(streak_key, 0) + 1 if reasons else 0
            if not reasons:
                hist.append({"avail": m["avail"], "price": m["price"]})
                del hist[:-HISTORY]
            if st[streak_key] >= 2:
                problems.append((label, "; ".join(reasons)))

            price = f", от {m['price']:.0f} €" if m["price"] else ""
            res.digest.append(f"• {label}: свободно {m['avail']:.0%} рейсов на 48 ч{price}")

        for label, why in problems:
            res.signals.append(Signal(
                id=f"ferries:{label}", group="ferries", tier=PREPARE if len(problems) == len(ROUTES) else WATCH,
                title=f"🛳 Паромы {label}: {why}", url="https://booking.tallink.com/"))
        return res
