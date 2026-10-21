from datetime import datetime, timedelta, timezone

from bot.config import LEAVE, PREPARE
from bot.sources import news

T0 = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


class Resp:
    def __init__(self, text):
        self.text = text


def rss(*titles):
    items = "".join(f"<item><title>{t}</title><link>https://x/{abs(hash(t))}</link>"
                    f"<guid>{abs(hash(t))}</guid></item>" for t in titles)
    return f"<rss><channel>{items}</channel></rss>"


def setup(monkeypatch, feeds: dict):
    monkeypatch.setattr(news, "FEEDS", [(outlet, url) for url, (outlet, _) in feeds.items()])
    monkeypatch.setattr(news.http, "get", lambda url, **kw: Resp(rss(*feeds[url][1])))


def test_baseline_unconfirmed_confirmed_and_cooldown(monkeypatch):
    feeds = {"err": ("ERR", ["Old news: martial law declared in Estonia"]), "pm": ("Postimees", [])}
    setup(monkeypatch, feeds)
    src, st = news.EstonianNews(), {}

    assert src.collect(st, T0).signals == []  # baseline: existing items are ignored
    st["initialized"] = True

    feeds["err"][1].append("Riigikogu kuulutas välja sõjaseisukorra")
    sigs = src.collect(st, T0 + timedelta(hours=1)).signals
    assert [(s.tier, "Не подтверждено" in s.title) for s in sigs] == [(PREPARE, True)]

    feeds["err"][1].append("Estonia declares martial law after border attack")  # same outlet: no confirmation
    feeds["pm"][1].append("В Эстонии объявлено военное положение")  # second outlet confirms
    sigs = src.collect(st, T0 + timedelta(hours=2)).signals
    assert [s.tier for s in sigs] == [LEAVE]  # per-category cooldown suppresses the extra single-outlet hits
    assert "ERR + Postimees" in sigs[0].title
