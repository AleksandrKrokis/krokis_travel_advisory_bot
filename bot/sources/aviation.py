"""Aviation: FAA prohibitions, EASA conflict zone bulletins, live air traffic."""

import re
import statistics
from datetime import datetime

from .. import http
from ..config import LEAVE, PREPARE
from ..signals import Signal, SourceResult

HOME_NAMES = ["Estonia", "Tallinn"]
NEIGHBOR_NAMES = ["Latvia", "Riga", "Lithuania", "Vilnius", "Finland", "Helsinki", "Poland", "Baltic Sea"]


def _name_tier(text: str) -> tuple[int, str]:
    for n in HOME_NAMES:
        if re.search(rf"\b{n}\b", text):
            return LEAVE, n
    for n in NEIGHBOR_NAMES:
        if re.search(rf"\b{n}\b", text):
            return PREPARE, n
    return 0, ""


class FAAProhibitions:
    """US carriers are banned from conflict airspace via KICZ NOTAMs/SFARs."""
    name = "faa"
    title = "FAA: запреты полётов"
    interval_hours = 3
    URL = "https://www.faa.gov/air_traffic/publications/us_restrictions"

    def collect(self, st: dict, now) -> SourceResult:
        text = http.strip_html(http.get(self.URL).text)
        if "KICZ" not in text:
            raise RuntimeError("unexpected page layout")
        res = SourceResult()
        for n in HOME_NAMES + NEIGHBOR_NAMES:
            if re.search(rf"\b{n}\b", text):
                tier, _ = _name_tier(n)
                res.signals.append(Signal(
                    id=f"faa:{n}", group="faa", tier=tier, url=self.URL,
                    title=f"✈️ FAA: ограничения полётов для авиакомпаний США — {n}"))
        return res


class EASAConflictZones:
    name = "czib"
    title = "EASA: бюллетени о зонах конфликта"
    interval_hours = 3
    URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs"
    ARCHIVE = "https://web.archive.org/web/2026id_/" + URL

    def _rows(self, page: str) -> list[str]:
        rows = []
        for tr in re.findall(r"<tr.*?</tr>", page, re.S):
            cells = [http.strip_html(c) for c in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S)]
            subj = next((c for c in cells if "CZIB" in c), None)
            if subj:
                rows.append(subj)
        return rows

    def collect(self, st: dict, now) -> SourceResult:
        rows = []
        for url in (self.URL, self.ARCHIVE):  # EASA site has long maintenance windows
            try:
                rows = self._rows(http.get(url, retries=1).text)
            except Exception as e:
                print(f"  czib {url}: {e}")
            if rows:
                break
        if not rows:
            raise RuntimeError("no CZIB rows parsed")
        res = SourceResult()
        for subj in rows:
            if "active" not in subj.lower():
                continue
            tier, n = _name_tier(subj)
            m = re.search(r"CZIB-?(\d{4}-\d{2})", subj)
            if tier and m:
                res.signals.append(Signal(
                    id=f"czib:{m.group(1)}", group="czib", tier=tier, url=self.URL,
                    title=f"✈️ EASA: бюллетень о зоне конфликта — {subj[:120]}"))
        return res


# Bounding boxes (lamin, lomin, lamax, lomax)
ESTONIA_BOX = (57.5, 21.5, 59.8, 28.3)
CONTROL_BOX = (55.0, 10.0, 57.0, 14.5)  # Denmark / southern Sweden: detects data outages
SAMPLES_PER_HOUR = 7


def _count(box) -> int:
    lamin, lomin, lamax, lomax = box
    d = http.get("https://opensky-network.org/api/states/all",
                 params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}, retries=1).json()
    return sum(1 for s in d.get("states") or [] if not s[8])  # s[8] = on_ground


class AirTraffic:
    """Airspace emptying over Estonia vs the same hour on previous days."""
    name = "opensky"
    title = "OpenSky: трафик над Эстонией"
    interval_hours = 1

    def collect(self, st: dict, now: datetime) -> SourceResult:
        hour = str(now.hour)
        est, ctl = _count(ESTONIA_BOX), _count(CONTROL_BOX)
        h_est = st.setdefault("est", {}).setdefault(hour, [])
        h_ctl = st.setdefault("ctl", {}).setdefault(hour, [])
        res = SourceResult()

        low = False
        if len(h_est) >= 4:
            med_est, med_ctl = statistics.median(h_est), statistics.median(h_ctl)
            if med_est >= 10 and est < 0.25 * med_est and ctl >= 0.6 * med_ctl:
                low = True
            res.digest.append(f"• Самолётов над Эстонией: {est} (обычно в этот час ~{med_est:.0f})")
        st["low_runs"] = st.get("low_runs", 0) + 1 if low else 0

        if not low:  # keep the baseline clean of anomalies
            h_est.append(est)
            h_ctl.append(ctl)
            del h_est[:-SAMPLES_PER_HOUR], h_ctl[:-SAMPLES_PER_HOUR]

        if st["low_runs"] >= 2:
            res.signals.append(Signal(
                id="opensky:empty", group="opensky", tier=PREPARE,
                url="https://www.flightradar24.com/59.4,24.8/7",
                title=f"✈️ Небо над Эстонией опустело: {est} самолётов при норме ~{statistics.median(h_est):.0f}",
                detail="Проверка на соседнем регионе показывает нормальный трафик, значит это не сбой данных."))
        return res
