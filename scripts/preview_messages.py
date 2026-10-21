#!/usr/bin/env python3
"""Print example messages for typical scenarios. Never sends anything."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import messages  # noqa: E402
from bot.config import LEAVE, PREPARE, WATCH  # noqa: E402

NOW = datetime(2026, 10, 26, 6, 17, tzinfo=timezone.utc)


def s(id, group, tier, title, detail="", url="https://example.org"):
    return {"id": id, "group": group, "tier": tier, "title": title, "detail": detail, "url": url}


def show(name, html):
    text = re.sub(r'<a href="[^"]*">([^<]*)</a>', r"[\1]", html)
    text = re.sub(r"<[^>]+>", "", text)
    print(f"\n──────── {name} ────────\n{text}")


pm = s("polymarket:invade_nato", "polymarket", PREPARE,
       "📈 Polymarket: «Россия нападёт на страну НАТО» до 31.12.2027 — 27.0% (+9.5 п.п. за 7 дн.)")
fcdo = s("fcdo:EE", "fcdo", PREPARE, "🇬🇧 МИД Великобритании: Эстония — только необходимые поездки (вся страна)")
art4 = s("news:article4", "news", PREPARE, "📰 ERR: консультации НАТО по статье 4",
         "Estonia requests NATO Article 4 consultations after drone incursion")
gd = s("gdelt:rhetoric", "gdelt", WATCH, "🌐 GDELT: Риторика российских СМИ о Прибалтике — всплеск x3.4 к норме")
ferry = s("ferries:sto", "ferries", WATCH, "🛳 Паромы Таллинн → Стокгольм: цена 310 € при обычной ~95 €")

show("1. Новый сигнал, общий уровень не меняется",
     messages.new_signals([art4], 1, NOW))
show("2. Уровень повышен до ГОТОВИТЬСЯ",
     messages.level_up(1, 2, [pm], [pm, art4, gd], NOW))
show("3. Уровень повышен до УЕЗЖАТЬ",
     messages.level_up(2, 3, [s("faa:Estonia", "faa", LEAVE,
                                "✈️ FAA: ограничения полётов для авиакомпаний США — Estonia"), fcdo],
                       [pm, art4, gd, ferry], NOW))
show("4. Новость о решении, пока не подтверждена вторым изданием",
     messages.new_signals([s("news:war", "news", PREPARE, "📰 ⚠️ Не подтверждено: ERR: в Эстонии объявлено военное положение",
                             "Riigikogu kuulutas välja sõjaseisukorra")], 1, NOW))
show("5. Уровень снижен",
     messages.level_down(2, 1, [gd], NOW))

sst = {
    "polymarket": {"digest": [
        "• Россия нападёт на страну НАТО до 31.12.2026: <b>4.5%</b> (+0.3 п.п. за 7 дн.)",
        "• Военные действия России против страны ЕС до 31.12.2026: <b>9.5%</b> (-0.5 п.п. за 7 дн.)",
        "• Применение статьи 5 НАТО до 31.12.2026: <b>4.6%</b> (+0.1 п.п. за 7 дн.)",
        "• Военное столкновение НАТО и России до 31.12.2026: <b>26.5%</b> (+1.0 п.п. за 7 дн.)",
        "• Перемирие Россия–Украина до 31.12.2026: <b>11.5%</b> (-2.0 п.п. за 7 дн.)"]},
    "ferries": {"digest": ["• Таллинн → Хельсинки: свободно 100% рейсов на 48 ч, от 22 €",
                           "• Таллинн → Стокгольм: свободно 100% рейсов на 48 ч, от 88 €"]},
    "gdelt": {"digest": ["• Риторика российских СМИ о Прибалтике: x1.1 к норме за последние 3 дн.",
                         "• Военная тема вокруг Балтии в мировых СМИ: x0.9 к норме за последние 3 дн."]},
    "opensky": {"digest": ["• Самолётов над Эстонией: 41 (обычно в этот час ~44)"]},
}
events = [
    {"ts": NOW.isoformat(), "tier": WATCH, "title": "", "url": "https://news.err.ee/",
     "detail": "Russian fighter jet violated Estonian airspace near Vaindloo for 2 minutes"},
    {"ts": NOW.isoformat(), "tier": WATCH, "title": "", "url": "https://news.err.ee/",
     "detail": "Finnish police investigate damage to Gulf of Finland data cable"},
]
show("6. Еженедельная сводка (понедельник, ~09:17 по Таллинну)",
     messages.digest("weekly", 0, [], events, sst, NOW))
show("7. Админ-чат: источник не отвечает (в канал не уходит)",
     messages.source_failed("EASA: бюллетени о зонах конфликта", "RuntimeError: no CZIB rows parsed",
                            datetime(2026, 10, 25, 18, 17, tzinfo=timezone.utc)))
