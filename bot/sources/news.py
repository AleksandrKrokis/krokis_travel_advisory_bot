"""Estonian news (ERR, Postimees in EN/ET/RU) and US Embassy Tallinn alerts.

Noise control:
- Only headlines are matched, with strict co-occurrence rules.
- Most rules are WATCH (digest only).
- "Decision" rules (war state, mobilisation, armed attack) are PREPARE when a
  single outlet reports them and become LEAVE only after a second,
  independent outlet confirms within CONFIRM_HOURS.
"""

import re
from datetime import datetime, timedelta

from .. import http
from ..config import LEAVE, PREPARE, WATCH
from ..signals import Signal, SourceResult

FEEDS = [
    ("ERR", "https://news.err.ee/rss"),
    ("ERR", "https://www.err.ee/rss"),
    ("ERR", "https://rus.err.ee/rss"),
    ("Postimees", "https://news.postimees.ee/rss"),
    ("Postimees", "https://www.postimees.ee/rss"),
    ("Postimees", "https://rus.postimees.ee/rss"),
]
CONFIRM_HOURS = 12
CATEGORY_COOLDOWN_HOURS = 24
SEEN_LIMIT = 3000


def rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


EST = rx(r"eesti", r"estonia", r"эстони", r"narva", r"нарв", r"ida-viru", r"ида-виру", r"tallinn", r"таллин")
RUS = rx(r"\brussia", r"venemaa", r"vene\b", r"росси", r"\bрф\b", r"kremlin", r"kreml", r"кремл", r"putin", r"путин")
DECLARED = rx(r"declar", r"announc", r"impos", r"introduc", r"kuulut", r"kehtest", r"välja", r"объяв", r"введ", r"ввод")
CYBER = rx(r"cyber", r"küber", r"кибер", r"ddos", r"hack", r"häkk", r"хакер")
OTHER_COUNTRY = rx(r"ukrain", r"украин", r"latvia", r"läti", r"латви", r"lithuania", r"leedu", r"литв", r"poland", r"poola",
                   r"польш", r"finland", r"soome", r"финлянд", r"russia", r"venemaa", r"росси", r"israel", r"iisrael", r"израил")
HYPOTHETICAL = rx(r"\bif\b", r"\bwould\b", r"\bcould\b", r"exercise", r"drill", r"õppus", r"учени", r"\bkui\b", r"\bесли\b",
                  r"scenario", r"stsenaarium", r"сценари", r"\blaw\b", r"seadus", r"закон", r"bill\b", r"eelnõu", r"законопроект")

# (category, tier, decisive, label, required patterns, forbidden patterns)
RULES = [
    # --- decisions: need confirmation by 2 outlets for LEAVE
    ("war_state", LEAVE, True, "в Эстонии объявлено военное положение",
     [rx(r"sõjaseisuk", r"state of war", r"martial law", r"военное положение"), DECLARED], [HYPOTHETICAL, OTHER_COUNTRY]),
    ("emergency", LEAVE, True, "в Эстонии объявлено чрезвычайное положение",
     [rx(r"erakorral\w* seisuk"), DECLARED], [HYPOTHETICAL, OTHER_COUNTRY]),
    ("emergency", LEAVE, True, "в Эстонии объявлено чрезвычайное положение",
     [rx(r"state of emergency", r"чрезвычайное положение"), DECLARED, EST], [HYPOTHETICAL, OTHER_COUNTRY]),
    ("ee_mobilisation", LEAVE, True, "в Эстонии объявлена мобилизация",
     [rx(r"mobilisat", r"mobiliz", r"мобилизац"), DECLARED], [RUS, HYPOTHETICAL]),
    ("attack", LEAVE, True, "сообщения о вооружённом нападении на Эстонию",
     [rx(r"attack", r"rünna", r"rünnak", r"нападен", r"атак", r"invasion", r"invade", r"sissetung", r"вторжен"), EST,
      rx(r"military", r"armed", r"troops", r"soldier", r"sõjav", r"relv", r"войск", r"военн", r"вооруж", r"missile",
         r"rakett", r"ракет", r"drone", r"droon", r"дрон", r"беспилот")],
     [CYBER, HYPOTHETICAL]),
    ("article5", LEAVE, True, "НАТО задействует статью 5",
     [rx(r"article 5", r"artikkel 5", r"artikli 5", r"5\. artikl", r"стать[яиюе] 5", r"пятой стать"),
      rx(r"invok", r"trigger", r"activat", r"käivit", r"rakend", r"задейств", r"применил", r"примен[её]н", r"привед")],
     [HYPOTHETICAL]),
    ("ru_mobilisation", PREPARE, True, "в России объявлена мобилизация",
     [rx(r"mobilisat", r"mobiliz", r"мобилизац"), RUS, DECLARED], [HYPOTHETICAL, rx(r"partial", r"osalise", r"частичн")]),
    # --- prepare
    ("article4", PREPARE, False, "консультации НАТО по статье 4",
     [rx(r"article 4", r"artikkel 4", r"artikli 4", r"4\. artikl", r"стать[яиюе] 4", r"четв[её]ртой стать")], []),
    ("embassy_evac", PREPARE, False, "посольство вывозит сотрудников или семьи",
     [rx(r"embass", r"saatkon", r"посольств", r"diplomat", r"дипломат"),
      rx(r"evacu", r"evaku", r"эвакуа", r"famil", r"perede", r"семь", r"withdraw", r"отзыв", r"leave", r"lahku", r"покида")],
     [rx(r"expel", r"välja saat", r"persona non grata", r"высыла", r"выслан")]),
    ("airspace_closed", PREPARE, False, "закрытие воздушного пространства",
     [rx(r"airspace", r"õhuruum", r"воздушн\w* пространств"), rx(r"clos", r"sulg", r"sulet", r"закры")], []),
    # --- watch (digest only)
    ("airspace_violation", WATCH, False, "нарушение воздушного пространства",
     [rx(r"airspace", r"õhuruum", r"воздушн\w* пространств"), rx(r"violat", r"rikk", r"наруш")], []),
    ("cable", WATCH, False, "повреждение подводной инфраструктуры",
     [rx(r"cable", r"kaab", r"кабел", r"pipeline", r"gaasitoru", r"газопровод", r"estlink", r"balticconnector"),
      rx(r"damag", r"kahjust", r"поврежд", r"sabota", r"диверс", r"\bcut\b", r"rebenen", r"разрыв", r"anchor", r"ankru", r"якор")],
     []),
    ("troops", WATCH, False, "передвижения войск у границы",
     [rx(r"troops", r"forces", r"buildup", r"build-up", r"väed", r"vägede", r"войск", r"группировк"),
      rx(r"border", r"piir", r"границ", r"pskov", r"pihkva", r"псков", r"kaliningrad", r"калининград",
         r"leningrad", r"ленинград", r"luga", r"луга")], [rx(r"ukrain", r"ukrain", r"украин")]),
    ("narva", WATCH, False, "инцидент в Нарве или на границе",
     [rx(r"narva", r"нарв", r"koidula", r"luhamaa", r"piiripunkt", r"border crossing", r"пункт пропуска", r"кпп"),
      rx(r"provok", r"провокац", r"buoy", r"poi", r"буй", r"буи", r"incident", r"intsident", r"инцидент", r"clos",
         r"sulg", r"закры", r"detain", r"kinni", r"задерж")], []),
    ("cyber", WATCH, False, "крупная кибератака",
     [CYBER, rx(r"attack", r"rünn", r"атак"), EST], []),
    ("intel", WATCH, False, "оценка угрозы спецслужбами",
     [rx(r"välisluure", r"foreign intelligence", r"внешней разведки", r"kapo", r"kaitsepolitsei", r"полиция безопасности"),
      rx(r"threat", r"\boht", r"угроз", r"attack", r"rünn", r"напад", r"war\b", r"sõda", r"войн")], []),
]


def match_rules(title: str) -> list[tuple]:
    hits = []
    for rule in RULES:
        cat, tier, decisive, label, req, forbid = rule
        if all(p.search(title) for p in req) and not any(p.search(title) for p in forbid):
            hits.append(rule)
    return hits


class EstonianNews:
    name = "news"
    title = "Новости ERR / Postimees"
    interval_hours = 1

    def collect(self, st: dict, now: datetime) -> SourceResult:
        seen: list = st.setdefault("seen", [])
        seen_set = set(seen)
        baseline = not st.get("initialized")
        decisive: dict = st.setdefault("decisive", {})  # cat -> [{outlet, ts, title, url}]
        cat_last: dict = st.setdefault("cat_last", {})  # cat -> ts of last emitted signal
        res = SourceResult()
        ok = 0
        for outlet, url in FEEDS:
            try:
                items = http.parse_rss(http.get(url).text)
                ok += 1
            except Exception as e:
                print(f"  news feed failed {url}: {e}")
                continue
            for it in items:
                if it["guid"] in seen_set:
                    continue
                seen_set.add(it["guid"])
                seen.append(it["guid"])
                if baseline:
                    continue
                for cat, tier, is_decisive, label, _, _ in match_rules(it["title"]):
                    if is_decisive:
                        decisive.setdefault(cat, []).append(
                            {"outlet": outlet, "ts": now.isoformat(), "title": it["title"], "url": it["link"]})
                    # One signal per category per day: a big story yields dozens of articles
                    last = cat_last.get(cat)
                    if last and now - datetime.fromisoformat(last) < timedelta(hours=CATEGORY_COOLDOWN_HOURS):
                        continue
                    cat_last[cat] = now.isoformat()
                    single_tier = PREPARE if is_decisive and tier == LEAVE else tier
                    prefix = "⚠️ Не подтверждено: " if is_decisive and tier == LEAVE else ""
                    res.signals.append(Signal(
                        id=f"news:{cat}:{it['guid']}", group="news", tier=single_tier, kind="event",
                        title=f"📰 {prefix}{outlet}: {label}", detail=it["title"], url=it["link"]))
        if ok == 0:
            raise RuntimeError("all news feeds failed")
        del seen[:-SEEN_LIMIT]

        # Confirmation by two independent outlets
        cutoff = now - timedelta(hours=CONFIRM_HOURS)
        for cat in list(decisive):
            decisive[cat] = [h for h in decisive[cat] if datetime.fromisoformat(h["ts"]) >= cutoff]
            if not decisive[cat]:
                del decisive[cat]
                continue
            outlets = {h["outlet"] for h in decisive[cat]}
            rule = next(r for r in RULES if r[0] == cat)
            if len(outlets) >= 2:
                first = decisive[cat][0]
                res.signals.append(Signal(
                    id=f"news:confirmed:{cat}:{'%d-W%02d' % now.isocalendar()[:2]}", group="news_confirmed",
                    tier=rule[1],
                    kind="event", title=f"📰 Подтверждено ({' + '.join(sorted(outlets))}): {rule[3]}",
                    detail=first["title"], url=first["url"]))
        return res


EMBASSY_LEAVE = rx(r"ordered departure", r"\bdepart\w* (estonia|the country)", r"\bleave (estonia|the country)",
                   r"shelter in place", r"evacuat")
EMBASSY_PREPARE = rx(r"authorized departure", r"military", r"airspace", r"drone", r"missile", r"attack", r"conflict",
                     r"consider (leaving|departing)", r"commercial (flights|options)", r"step program", r"\bSTEP\b")


class USEmbassyTallinn:
    name = "embassy"
    title = "Посольство США в Таллинне"
    interval_hours = 1

    def collect(self, st: dict, now: datetime) -> SourceResult:
        items = http.parse_rss(http.get("https://ee.usembassy.gov/feed/").text)
        res = SourceResult()
        for it in items:
            cats = " ".join(it["categories"]).lower()
            if "alert" not in it["title"].lower() and "alert" not in cats:
                continue
            text = f"{it['title']} {it['description']}"
            if EMBASSY_LEAVE.search(text):
                tier = LEAVE
            elif EMBASSY_PREPARE.search(text) or "security alert" in it["title"].lower():
                tier = PREPARE
            else:
                tier = WATCH
            res.signals.append(Signal(
                id=f"embassy:{it['guid']}", group="embassy", tier=tier, kind="event",
                title="🇺🇸 Посольство США в Таллинне: предупреждение", detail=it["title"], url=it["link"]))
        return res
