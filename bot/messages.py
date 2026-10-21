"""Telegram message texts (HTML parse mode)."""

from datetime import datetime
from html import escape

from .config import LEVEL_ADVICE, LEVELS, TZ

TIER_ICON = {1: "🟡", 2: "🟠", 3: "🔴"}
MAX_LEN = 4000


def _level(n: int) -> str:
    icon, name = LEVELS[n]
    return f"{icon} <b>{name}</b>"


def _when(now: datetime) -> str:
    return f"<i>{now.astimezone(TZ).strftime('%d.%m.%Y %H:%M')} (Таллинн)</i>"


def _sig(s: dict, with_detail: bool = True) -> str:
    line = f"{TIER_ICON.get(s['tier'], '⚪')} {escape(s['title'])}"
    if with_detail and s.get("detail"):
        line += f"\n    <i>{escape(s['detail'][:200])}</i>"
    if s.get("url"):
        line += f'\n    <a href="{escape(s["url"], quote=True)}">источник</a>'
    return line


def _sorted(signals: list[dict]) -> list[dict]:
    return sorted(signals, key=lambda s: (-s["tier"], s["title"]))


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LEN else text[:MAX_LEN - 20].rsplit("\n", 1)[0] + "\n…"


def level_up(prev: int, cur: int, new: list[dict], active: list[dict], now: datetime) -> str:
    new_ids = {s["id"] for s in new}
    lines = [f"{LEVELS[cur][0]} <b>Уровень угрозы повышен: {LEVELS[cur][1]}</b>",
             f"Был: {_level(prev)}", ""]
    if new:
        lines += ["<b>Что изменилось:</b>"] + [_sig(s) for s in _sorted(new)] + [""]
    rest = [s for s in _sorted(active) if s["id"] not in new_ids]
    if rest:
        lines += ["<b>Также активно:</b>"] + [_sig(s, with_detail=False) for s in rest[:8]] + [""]
    lines += [f"<b>Что делать:</b> {LEVEL_ADVICE[cur]}", "", _when(now)]
    return _clip("\n".join(lines))


def level_down(prev: int, cur: int, active: list[dict], now: datetime) -> str:
    lines = [f"{LEVELS[cur][0]} <b>Уровень угрозы снижен: {LEVELS[cur][1]}</b>",
             f"Был: {_level(prev)}. Новых тревожных сигналов не было 3 дня.", ""]
    if active:
        lines += ["<b>Ещё активно:</b>"] + [_sig(s, with_detail=False) for s in _sorted(active)[:8]] + [""]
    lines.append(_when(now))
    return _clip("\n".join(lines))


def new_signals(new: list[dict], level: int, now: datetime) -> str:
    head = "Новый сигнал" if len(new) == 1 else f"Новые сигналы ({len(new)})"
    icon = TIER_ICON[max(s["tier"] for s in new)]
    lines = [f"{icon} <b>{head}</b>", ""] + [_sig(s) for s in _sorted(new)] + [
        "", f"Общий уровень: {_level(level)} (без изменений)", _when(now)]
    return _clip("\n".join(lines))


def digest(kind: str, level: int, active: list[dict], events: list[dict], sst: dict, now: datetime) -> str:
    title = "📋 <b>Еженедельная сводка</b>" if kind == "weekly" else "📋 <b>Ежедневная сводка</b>"
    lines = [title, f"Уровень угрозы: {_level(level)}", f"<i>{LEVEL_ADVICE[level]}</i>", ""]

    if active:
        lines += ["<b>Активные сигналы:</b>"] + [_sig(s, with_detail=False) for s in _sorted(active)[:10]] + [""]

    period = "неделю" if kind == "weekly" else "сутки"
    if events:
        lines.append(f"<b>События за {period} ({len(events)}):</b>")
        for e in sorted(events, key=lambda e: (-e["tier"], e["ts"]))[:10]:
            text = e["detail"] or e["title"]
            link = f' — <a href="{escape(e["url"], quote=True)}">→</a>' if e.get("url") else ""
            lines.append(f"{TIER_ICON.get(e['tier'], '⚪')} {escape(text[:140])}{link}")
        lines.append("")
    else:
        lines += [f"За {period} тревожных событий не было.", ""]

    for name, header in (("polymarket", "📈 <b>Прогнозы Polymarket:</b>"), ("ferries", "🛳 <b>Паромы:</b>"),
                         ("gdelt", "🌐 <b>Мировые СМИ (GDELT):</b>"), ("opensky", "✈️ <b>Авиатрафик:</b>")):
        d = sst.get(name, {}).get("digest")
        if d:
            lines += [header] + d + [""]

    lines.append(_when(now))
    return _clip("\n".join(lines))


def source_failed(title: str, error: str, since: datetime) -> str:
    return (f"⚙️ <b>Источник не отвечает:</b> {escape(title)}\n"
            f"С {since.astimezone(TZ).strftime('%d.%m %H:%M')}\n<code>{escape(error)}</code>")


def source_recovered(title: str) -> str:
    return f"⚙️ ✅ Источник снова работает: {escape(title)}"
