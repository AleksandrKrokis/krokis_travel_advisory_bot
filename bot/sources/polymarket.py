"""Polymarket prediction markets.

Markets are discovered by search (events roll over: "...by Dec 31, 2026",
"...by Dec 31, 2027"), picking the nearest deadline at least MIN_HORIZON_DAYS
away. Thresholds use hysteresis so a market hovering at a boundary does not
flap.
"""

import json
import re
from datetime import datetime, timedelta

from .. import http
from ..config import PREPARE, WATCH
from ..signals import Signal, SourceResult

API = "https://gamma-api.polymarket.com"
MIN_HORIZON_DAYS = 45
MIN_VOLUME = 50_000
HYSTERESIS = 0.8  # stay in a tier until price falls below threshold * 0.8
HISTORY_DAYS = 21

TRACKED = [
    # key, label, search query, question regex, thresholds (WATCH, PREPARE), 7-day jump for WATCH
    ("invade_nato", "Россия нападёт на страну НАТО", "Russia invade NATO country",
     r"russia invade a nato country", (0.12, 0.25), 0.07),
    ("eu_action", "Военные действия России против страны ЕС", "Russia military action against EU country",
     r"russia military action against an eu country", (0.20, 0.35), 0.08),
    ("article5", "Применение статьи 5 НАТО", "NATO article 5",
     r"nato article 5", (0.12, 0.25), 0.07),
    # Fuzzy definition (any incident counts) and already high, so only sharp jumps matter
    ("nato_clash", "Военное столкновение НАТО и России", "NATO Russia military clash",
     r"nato x russia military clash", None, 0.15),
    # A frozen Ukraine front frees Russian forces: strategic WATCH only
    ("ceasefire", "Перемирие Россия–Украина", "Russia Ukraine ceasefire",
     r"russia x ukraine ceasefire by", (0.5, None), None),
]


def _search(query: str) -> list[dict]:
    r = http.get(f"{API}/public-search", params={"q": query, "limit_per_type": 20, "events_status": "active"})
    return r.json().get("events") or []


def pick_market(events: list[dict], question_rx: str, now: datetime) -> dict | None:
    rxq = re.compile(question_rx, re.I)
    candidates = []
    for e in events:
        if e.get("closed"):
            continue
        for m in e.get("markets") or []:
            if m.get("closed") or not m.get("active", True) or not rxq.search(m.get("question", "")):
                continue
            try:
                end = datetime.fromisoformat(m["endDate"].replace("Z", "+00:00"))
                price = float(json.loads(m["outcomePrices"])[0])
            except (KeyError, ValueError, TypeError):
                continue
            vol = float(m.get("volumeNum") or m.get("volume") or e.get("volume") or 0)
            candidates.append({"id": str(m.get("id")), "question": m["question"], "end": end, "price": price,
                               "volume": vol, "slug": e.get("slug")})
    if not candidates:
        return None
    far = [c for c in candidates if c["end"] >= now + timedelta(days=MIN_HORIZON_DAYS)]
    pool = far or candidates
    return min(pool, key=lambda c: c["end"]) if far else max(pool, key=lambda c: c["end"])


def tier_for(price: float, thresholds, prev_tier: int) -> int:
    if not thresholds:
        return 0
    tier = 0
    for t, thr in enumerate(thresholds, start=1):
        if thr is None:
            continue
        limit = thr * HYSTERESIS if prev_tier >= t else thr
        if price >= limit:
            tier = t
    return tier


class Polymarket:
    name = "polymarket"
    title = "Polymarket"
    interval_hours = 1

    def collect(self, st: dict, now: datetime) -> SourceResult:
        hist: dict = st.setdefault("history", {})
        tiers: dict = st.setdefault("tiers", {})
        res = SourceResult()
        found = 0
        today = now.date().isoformat()
        for key, label, query, qrx, thresholds, jump in TRACKED:
            m = pick_market(_search(query), qrx, now)
            if not m:
                res.digest.append(f"• {label}: рынок не найден")
                continue
            found += 1
            h = hist.setdefault(m["id"], {})
            h[today] = round(m["price"], 4)
            for d in sorted(h)[:-HISTORY_DAYS]:
                del h[d]
            week_ago = (now - timedelta(days=7)).date().isoformat()
            past = [d for d in sorted(h) if d <= week_ago]
            delta = m["price"] - h[past[-1]] if past else None

            low_volume = m["volume"] < MIN_VOLUME
            tier = 0 if low_volume else tier_for(m["price"], thresholds, tiers.get(key, 0))
            if key == "ceasefire":
                tier = min(tier, WATCH)
            if jump and delta is not None and delta >= jump and not low_volume:
                tier = max(tier, WATCH)
            tiers[key] = tier

            pct = f"{m['price'] * 100:.1f}%"
            dtxt = f" ({delta * 100:+.1f} п.п. за 7 дн.)" if delta is not None else ""
            deadline = (m["end"] - timedelta(minutes=1)).strftime("%d.%m.%Y")  # "by Dec 31" ends Jan 1 00:00
            url = f"https://polymarket.com/event/{m['slug']}"
            res.digest.append(f"• {label} до {deadline}: <b>{pct}</b>{dtxt}")
            if tier:
                res.signals.append(Signal(
                    id=f"polymarket:{key}", group="polymarket", tier=min(tier, PREPARE),
                    title=f"📈 Polymarket: «{label}» до {deadline} — {pct}{dtxt}", url=url))
        if found == 0:
            raise RuntimeError("no tracked markets found")
        # Forget markets not updated for a while (rolled over)
        for mid in [k for k, h in hist.items() if max(h) < (now - timedelta(days=HISTORY_DAYS)).date().isoformat()]:
            del hist[mid]
        return res
