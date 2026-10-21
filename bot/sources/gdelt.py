"""GDELT: spikes in world media coverage relative to the last 60 days.

Raw article counts are normalised by GDELT's total daily volume, and a spike
must be large both statistically (mean + 3σ) and in relative terms (x2.5).
"""

import statistics
import time
from urllib.parse import quote

from .. import http
from ..config import WATCH
from ..signals import Signal, SourceResult

QUERIES = [
    ("rhetoric", "Риторика российских СМИ о Прибалтике",
     '(Estonia OR Baltic OR Narva OR Эстония OR Прибалтика OR Нарва) '
     '(russophobia OR nazism OR genocide OR compatriots OR русофобия OR нацизм OR геноцид OR соотечественники) '
     'sourcecountry:RS'),
    ("military", "Военная тема вокруг Балтии в мировых СМИ",
     '(Estonia OR Baltic OR Narva OR Pskov OR Kaliningrad) '
     '(troops OR "military buildup" OR mobilization OR invasion OR "massing forces")'),
]
RECENT_DAYS = 3
MIN_RECENT_ARTICLES = 25


def spike(values: list[tuple[int, int]]) -> tuple[bool, float]:
    """values: [(count, norm)] oldest→newest, today's partial day excluded."""
    ratios = [c / n if n else 0.0 for c, n in values]
    base, recent = ratios[:-RECENT_DAYS], ratios[-RECENT_DAYS:]
    if len(base) < 30:
        return False, 0.0
    mu, sd = statistics.mean(base), statistics.pstdev(base)
    rmean = statistics.mean(recent)
    factor = rmean / mu if mu else 0.0
    raw_recent = sum(c for c, _ in values[-RECENT_DAYS:])
    return (rmean > mu + 3 * sd and factor >= 2.5 and raw_recent >= MIN_RECENT_ARTICLES), factor


class GDELT:
    name = "gdelt"
    title = "GDELT: мировые СМИ"
    interval_hours = 6

    def collect(self, st: dict, now) -> SourceResult:
        res = SourceResult()
        for i, (key, label, q) in enumerate(QUERIES):
            if i:
                time.sleep(6)  # GDELT allows one request per 5 seconds
            d = http.get("https://api.gdeltproject.org/api/v2/doc/doc",
                         params={"query": q, "mode": "timelinevolraw", "timespan": "70d", "format": "json"},
                         retries=2).json()
            series = d["timeline"][0]["data"]
            values = [(int(p["value"]), int(p.get("norm") or 0)) for p in series][:-1]
            is_spike, factor = spike(values)
            res.digest.append(f"• {label}: x{factor:.1f} к норме за последние {RECENT_DAYS} дн.")
            if is_spike:
                res.signals.append(Signal(
                    id=f"gdelt:{key}", group="gdelt", tier=WATCH,
                    title=f"🌐 GDELT: {label} — всплеск x{factor:.1f} к норме",
                    url="https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&format=html&timespan=3d&query="
                        + quote(q)))
        return res
