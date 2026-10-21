from datetime import datetime, timedelta, timezone

from bot.config import LEAVE, PREPARE, WATCH
from bot.engine import Engine, compute_level, load_state
from bot.signals import Signal, SourceResult

T0 = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)  # Wednesday


class FakeSource:
    def __init__(self, name, interval_hours=1):
        self.name = name
        self.title = name
        self.interval_hours = interval_hours
        self.signals: list[Signal] = []
        self.fail = False

    def collect(self, st, now):
        if self.fail:
            raise RuntimeError("down")
        return SourceResult(signals=list(self.signals))


def run(state, sources, now):
    e = Engine(state, sources, now)
    e.run_sources(force=True)
    e.decide()
    return e


def sig(id, group, tier, kind="state"):
    return Signal(id=id, group=group, tier=tier, title=id, kind=kind)


def test_compute_level():
    s = lambda g, t: {"group": g, "tier": t}
    assert compute_level([]) == 0
    assert compute_level([s("news", WATCH), s("news", WATCH)]) == 0  # one group never escalates alone
    assert compute_level([s("news", WATCH), s("gdelt", WATCH)]) == 1
    assert compute_level([s("fcdo", PREPARE)]) == 1
    assert compute_level([s("fcdo", PREPARE), s("aa", PREPARE)]) == 2
    assert compute_level([s("fcdo", PREPARE), s("news", WATCH), s("gdelt", WATCH)]) == 2
    assert compute_level([s("fcdo", PREPARE), s("aa", PREPARE), s("canada", PREPARE)]) == 3
    assert compute_level([s("faa", LEAVE)]) == 3


def test_first_run_and_baselines_are_silent():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a = FakeSource("a")
    a.signals = [sig("a1", "a", PREPARE)]
    e = run(st, [a], T0)
    assert e.channel == [] and e.admin == []
    assert st["level"]["current"] == 1

    # New source added later: its first run is a silent baseline too
    b = FakeSource("b")
    b.signals = [sig("b1", "b", PREPARE)]
    e = run(st, [a, b], T0 + timedelta(hours=1))
    assert e.channel and "повышен" in e.channel[0]  # level rose 1 -> 2 ...
    assert "b1" not in e.channel[0].split("Что изменилось")[-1].split("Также")[0]  # ... but b1 is not "new"


def test_prepare_signal_announced_once_watch_never():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a = FakeSource("a")
    run(st, [a], T0)
    a.signals = [sig("w", "a", WATCH)]
    e = run(st, [a], T0 + timedelta(hours=1))
    assert e.channel == []
    a.signals = [sig("w", "a", WATCH), sig("p", "a", PREPARE)]
    e = run(st, [a], T0 + timedelta(hours=2))
    assert len(e.channel) == 1 and "повышен" in e.channel[0]
    e = run(st, [a], T0 + timedelta(hours=3))
    assert e.channel == []  # same signal again: silent


def test_downgrade_needs_72h():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a, b = FakeSource("a"), FakeSource("b")
    run(st, [a, b], T0)
    a.signals, b.signals = [sig("a", "a", PREPARE)], [sig("b", "b", PREPARE)]
    run(st, [a, b], T0 + timedelta(hours=1))
    assert st["level"]["current"] == 2
    a.signals, b.signals = [], []
    for h in range(2, 72):
        e = run(st, [a, b], T0 + timedelta(hours=h))
        assert not any("снижен" in m for m in e.channel)
    e = run(st, [a, b], T0 + timedelta(hours=74))
    assert st["level"]["current"] == 0
    assert any("снижен" in m for m in e.channel)


def test_flapping_signal_does_not_respam():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a, b = FakeSource("a"), FakeSource("b")
    b.signals = [sig("b", "b", PREPARE)]
    run(st, [a, b], T0)
    sent = 0
    for h in range(1, 20):
        a.signals = [sig("x", "a", PREPARE)] if h % 2 else []
        sent += len(run(st, [a, b], T0 + timedelta(hours=h)).channel)
    assert sent == 1  # level went up once; stays up thanks to the 72h downgrade rule


def test_events_expire_and_never_return():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a = FakeSource("a")
    run(st, [a], T0)
    a.signals = [sig("ev", "a", PREPARE, kind="event")]
    assert run(st, [a], T0 + timedelta(hours=1)).channel
    assert "ev" in st["signals"]
    run(st, [a], T0 + timedelta(days=8))
    assert "ev" not in st["signals"]
    e = run(st, [a], T0 + timedelta(days=8, hours=1))
    assert "ev" not in st["signals"] and not any("Новый" in m for m in e.channel)


def test_failures_go_to_admin_once_and_keep_signals():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a = FakeSource("a")
    a.signals = [sig("s", "a", PREPARE)]
    run(st, [a], T0)
    a.fail = True
    admin = []
    for h in range(1, 20):
        e = run(st, [a], T0 + timedelta(hours=h))
        admin += e.admin
        assert e.channel == [] or all("сводка" in m for m in e.channel)
    assert len(admin) == 1 and "не отвечает" in admin[0]
    assert "s" in st["signals"]  # failing source keeps its last known signals
    a.fail = False
    assert any("снова работает" in m for m in run(st, [a], T0 + timedelta(hours=21)).admin)


def test_weekly_digest_on_monday_only_once():
    st = load_state(__import__("pathlib").Path("/nonexistent"))
    a = FakeSource("a")
    run(st, [a], T0)
    monday = datetime(2026, 10, 26, 5, 17, tzinfo=timezone.utc)
    digests = []
    for h in range(0, 30):
        digests += [m for m in run(st, [a], monday + timedelta(hours=h)).channel if "сводка" in m]
    assert len(digests) == 1 and "Еженедельная" in digests[0]
