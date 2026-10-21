"""Government travel advisories: US State Dept, UK FCDO, German AA, Canada.

All four expose structured status fields, so signals are raised on status
changes, never on routine text edits.
"""

import re

from .. import http
from ..config import COUNTRIES, HOME, LEAVE, PREPARE, WATCH
from ..signals import Signal, SourceResult


def _is_home(c: dict) -> bool:
    return c["iso2"] == HOME["iso2"]


def _scaled(tier: int, home: bool) -> int:
    """Neighbour advisories weigh one tier less than the home country."""
    return tier if home else max(0, tier - 1)


# ---------------------------------------------------------------- US State Dept

US_LEVEL_TIER = {"2": WATCH, "3": PREPARE, "4": LEAVE}
US_PHRASES = [
    (re.compile(r"ordered departure", re.I), LEAVE, "эвакуация сотрудников посольства (ordered departure)"),
    (re.compile(r"\b(depart|leave)\b[^.]{0,40}\b(immediately|now|as soon as possible)", re.I), LEAVE,
     "призыв немедленно покинуть страну"),
    (re.compile(r"authorized departure", re.I), PREPARE, "разрешён выезд семей сотрудников (authorized departure)"),
]


class USStateDept:
    name = "us_state"
    title = "Госдеп США"
    interval_hours = 1

    def collect(self, st: dict, now) -> SourceResult:
        data = http.get("https://cadataapi.state.gov/api/TravelAdvisories").json()
        by_country = {}
        for item in data:
            m = re.match(r"(.+?)\s*-\s*Level\s*(\d)", item.get("Title", ""))
            if m:
                by_country[m.group(1).strip()] = (m.group(2), item)
        if len(by_country) < 100:
            raise RuntimeError(f"only {len(by_country)} advisories parsed")

        res = SourceResult()
        for c in COUNTRIES:
            if c["name"] not in by_country:
                continue
            level, item = by_country[c["name"]]
            home = _is_home(c)
            link = item.get("Link", "")
            tier = _scaled(US_LEVEL_TIER.get(level, 0), home)
            if tier:
                res.signals.append(Signal(
                    id=f"us_state:level:{c['iso2']}", group="us_state", tier=tier,
                    title=f"🇺🇸 Госдеп: {c['ru']} — Level {level}", url=link))
            summary = http.strip_html(item.get("Summary", ""))
            for i, (rx, ptier, label) in enumerate(US_PHRASES):
                ptier = _scaled(ptier, home)
                if ptier and rx.search(summary):
                    res.signals.append(Signal(
                        id=f"us_state:phrase:{c['iso2']}:{i}", group="us_state", tier=ptier,
                        title=f"🇺🇸 Госдеп: {c['ru']} — {label}", url=link))
        return res


# ---------------------------------------------------------------- UK FCDO

FCDO_STATUS = {
    "avoid_all_travel_to_whole_country": (LEAVE, "не ездить совсем (вся страна)"),
    "avoid_all_but_essential_travel_to_whole_country": (PREPARE, "только необходимые поездки (вся страна)"),
    "avoid_all_travel_to_parts": (PREPARE, "не ездить в часть регионов"),
    "avoid_all_but_essential_travel_to_parts": (WATCH, "только необходимые поездки в часть регионов"),
}
FCDO_LEAVE_RX = re.compile(r"\b(leave|depart\w*|evacuat\w*|commercial (flights|options|routes))\b", re.I)


class FCDO:
    name = "fcdo"
    title = "МИД Великобритании"
    interval_hours = 1

    def collect(self, st: dict, now) -> SourceResult:
        res = SourceResult()
        for c in COUNTRIES:
            d = http.get(f"https://www.gov.uk/api/content/foreign-travel-advice/{c['fcdo']}").json()
            det = d["details"]
            home = _is_home(c)
            url = f"https://www.gov.uk/foreign-travel-advice/{c['fcdo']}"
            for status in det.get("alert_status") or []:
                tier, label = FCDO_STATUS.get(status, (0, status))
                tier = _scaled(tier, home)
                if tier:
                    res.signals.append(Signal(
                        id=f"fcdo:{c['iso2']}:{status}", group="fcdo", tier=tier,
                        title=f"🇬🇧 МИД Великобритании: {c['ru']} — {label}", url=url))
            change = det.get("change_description") or ""
            if home and FCDO_LEAVE_RX.search(change):
                res.signals.append(Signal(
                    id=f"fcdo:{c['iso2']}:change:{d.get('public_updated_at')}", group="fcdo", tier=PREPARE,
                    kind="event", title=f"🇬🇧 МИД Великобритании: {c['ru']} — обновление о выезде",
                    detail=change[:300], url=url))
        return res


# ---------------------------------------------------------------- German AA

AA_FLAGS = [
    ("warning", LEAVE, "Reisewarnung — предупреждение против поездок"),
    ("situationWarning", PREPARE, "предупреждение о ситуации в стране"),
    ("partialWarning", PREPARE, "Reisewarnung для части страны"),
    ("situationPartWarning", WATCH, "предупреждение о ситуации в части страны"),
]


class AuswaertigesAmt:
    name = "aa"
    title = "МИД Германии"
    interval_hours = 1

    def collect(self, st: dict, now) -> SourceResult:
        r = http.get("https://www.auswaertiges-amt.de/opendata/travelwarning").json()["response"]
        by_iso = {v.get("countryCode"): (k, v) for k, v in r.items() if isinstance(v, dict)}
        res = SourceResult()
        for c in COUNTRIES:
            if c["iso2"] not in by_iso:
                raise RuntimeError(f"country {c['iso2']} missing")
            key, v = by_iso[c["iso2"]]
            home = _is_home(c)
            for flag, tier, label in AA_FLAGS:
                tier = _scaled(tier, home)
                if tier and v.get(flag):
                    res.signals.append(Signal(
                        id=f"aa:{c['iso2']}:{flag}", group="aa", tier=tier,
                        title=f"🇩🇪 МИД Германии: {c['ru']} — {label}",
                        url=f"https://www.auswaertiges-amt.de/de/service/laender/{c['name'].lower()}-node"))
        return res


# ---------------------------------------------------------------- Canada

CA_STATE = {
    "1": (WATCH, "высокая осторожность"),
    "2": (PREPARE, "избегать поездок без необходимости"),
    "3": (LEAVE, "избегать любых поездок"),
}


class CanadaAdvisory:
    name = "canada"
    title = "МИД Канады"
    interval_hours = 1

    def collect(self, st: dict, now) -> SourceResult:
        data = http.get("https://data.international.gc.ca/travel-voyage/index-alpha-eng.json").json()["data"]
        res = SourceResult()
        for c in COUNTRIES:
            v = data.get(c["iso2"])
            if not v:
                raise RuntimeError(f"country {c['iso2']} missing")
            tier, label = CA_STATE.get(str(v.get("advisory-state")), (0, ""))
            tier = _scaled(tier, _is_home(c))
            if tier:
                res.signals.append(Signal(
                    id=f"canada:{c['iso2']}:{v.get('advisory-state')}", group="canada", tier=tier,
                    title=f"🇨🇦 МИД Канады: {c['ru']} — {label}",
                    url=f"https://travel.gc.ca/destinations/{v['eng']['url-slug']}"))
        return res
