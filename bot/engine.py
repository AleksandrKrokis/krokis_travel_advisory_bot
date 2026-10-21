"""Core loop: run sources, merge signals into state, decide what to send.

Anti-noise rules:
- A source's first successful run is a silent baseline.
- The very first composite level is stored silently.
- Only PREPARE/LEAVE signals are sent instantly; WATCH goes to the digest.
- A signal is announced once per tier (re-sent only if it escalates).
- The composite level goes up immediately but down only after it has been
  lower for DOWNGRADE_AFTER_HOURS.
- Source failures go to the admin chat only, after SOURCE_FAIL_ALERT_HOURS.
"""

import json
import traceback
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from . import messages
from .config import (DIGEST_HOUR_UTC, DOWNGRADE_AFTER_HOURS, LEAVE, PREPARE, SOURCE_FAIL_ALERT_HOURS, WATCH)
from .signals import Signal

MFA_GROUPS = {"us_state", "fcdo", "aa", "canada"}
LOG_DAYS = 14
RESOLVED_MEMORY_HOURS = 72
EXPIRED_LIMIT = 2000


def load_state(path: Path) -> dict:
    if path.exists():
        st = json.loads(path.read_text())
        if st.get("version") == 2:
            return st
    return {"version": 2, "sources": {}, "signals": {}, "expired": [], "level": None, "log": [], "digest": {}}


def save_state(path: Path, st: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, indent=1, ensure_ascii=False, sort_keys=True))


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def compute_level(signals: list[dict]) -> int:
    if any(s["tier"] >= LEAVE for s in signals):
        return 3
    prep = {s["group"] for s in signals if s["tier"] >= PREPARE}
    watch = {s["group"] for s in signals if s["tier"] >= WATCH}
    if len(prep & MFA_GROUPS) >= 3 or len(prep) >= 4:
        return 3
    if len(prep) >= 2 or (prep and len(watch) >= 3):
        return 2
    if prep or len(watch) >= 2:
        return 1
    return 0


class Engine:
    def __init__(self, state: dict, sources: list, now: datetime):
        self.st = state
        self.sources = sources
        self.now = now
        self.new_instant: list[dict] = []
        self.channel: list[str] = []
        self.admin: list[str] = []

    # ------------------------------------------------------------ sources

    def run_sources(self, force: bool = False) -> None:
        for src in self.sources:
            sst = self.st["sources"].setdefault(src.name, {"initialized": False, "data": {}})
            last = sst.get("last_run")
            if not force and last and self.now - _ts(last) < timedelta(hours=src.interval_hours, minutes=-10):
                continue
            sst["last_run"] = self.now.isoformat()
            print(f"[{src.name}] collecting")
            try:
                res = src.collect(sst["data"], self.now)
            except Exception as e:
                traceback.print_exc()
                sst.setdefault("fail_since", self.now.isoformat())
                sst["error"] = f"{type(e).__name__}: {e}"[:300]
                continue
            baseline = not sst["initialized"]
            self._merge(src.name, res.signals, baseline)
            sst["initialized"] = True
            sst["last_ok"] = self.now.isoformat()
            sst["digest"] = res.digest
            if sst.pop("fail_alerted", False):
                self.admin.append(messages.source_recovered(src.title))
            sst.pop("fail_since", None)
            sst.pop("error", None)
            print(f"[{src.name}] ok: {len(res.signals)} signals{' (baseline)' if baseline else ''}")

        for src in self.sources:
            sst = self.st["sources"][src.name]
            fs = sst.get("fail_since")
            if fs and not sst.get("fail_alerted") and self.now - _ts(fs) >= timedelta(hours=SOURCE_FAIL_ALERT_HOURS):
                sst["fail_alerted"] = True
                self.admin.append(messages.source_failed(src.title, sst.get("error", ""), _ts(fs)))

    def _merge(self, source: str, sigs: list[Signal], baseline: bool) -> None:
        signals = self.st["signals"]
        expired = set(self.st["expired"])
        resolved = self.st.setdefault("resolved", {})
        now = self.now.isoformat()
        reported = set()
        for sig in sigs:
            if sig.id in expired or sig.tier <= 0:
                continue
            reported.add(sig.id)
            cur = signals.get(sig.id)
            if cur is None:
                # A state signal that resolved recently and came back is not news
                recent = resolved.pop(sig.id, None)
                notified = sig.tier if baseline else (recent["notified_tier"] if recent else 0)
                cur = signals[sig.id] = {**asdict(sig), "source": source, "first_seen": now,
                                         "notified_tier": notified}
                if not baseline and not recent:
                    self.st["log"].append({"ts": now, "tier": sig.tier, "title": sig.title,
                                           "detail": sig.detail, "url": sig.url})
            else:
                cur.update(tier=sig.tier, title=sig.title, detail=sig.detail, url=sig.url)
            cur["last_seen"] = now
            if sig.tier > cur["notified_tier"]:
                if sig.tier >= PREPARE:
                    self.new_instant.append(cur)
                cur["notified_tier"] = sig.tier

        for sid, s in list(signals.items()):
            if s["source"] != source:
                continue
            if s["kind"] == "state" and sid not in reported:
                resolved[sid] = {"ts": now, "notified_tier": s["notified_tier"]}
                del signals[sid]
        cutoff = self.now - timedelta(hours=RESOLVED_MEMORY_HOURS)
        for sid in [k for k, v in resolved.items() if _ts(v["ts"]) < cutoff]:
            del resolved[sid]
        self._expire_events()

    def _expire_events(self) -> None:
        signals = self.st["signals"]
        for sid, s in list(signals.items()):
            if s["kind"] == "event" and self.now - _ts(s["first_seen"]) > timedelta(days=s["ttl_days"]):
                del signals[sid]
                self.st["expired"].append(sid)
        del self.st["expired"][:-EXPIRED_LIMIT]
        cutoff = self.now - timedelta(days=LOG_DAYS)
        self.st["log"] = [e for e in self.st["log"] if _ts(e["ts"]) >= cutoff]

    # ------------------------------------------------------------ decisions

    def decide(self) -> None:
        self._expire_events()
        active = list(self.st["signals"].values())
        computed = compute_level(active)
        lv = self.st["level"]
        now = self.now.isoformat()

        if lv is None:  # first run ever: no announcement, first digest next Monday
            self.st["level"] = {"current": computed, "since": now, "lower_since": None}
            self.st["digest"] = {"weekly": "%d-W%02d" % self.now.isocalendar()[:2], "daily": self.now.date().isoformat()}
            self.new_instant = []
            return

        prev = lv["current"]
        if computed > prev:
            lv.update(current=computed, since=now, lower_since=None)
            self.channel.append(messages.level_up(prev, computed, self.new_instant, active, self.now))
        else:
            if computed < prev:
                lv["lower_since"] = lv.get("lower_since") or now
                if self.now - _ts(lv["lower_since"]) >= timedelta(hours=DOWNGRADE_AFTER_HOURS):
                    lv.update(current=computed, since=now, lower_since=None)
                    self.channel.append(messages.level_down(prev, computed, active, self.now))
            else:
                lv["lower_since"] = None
            if self.new_instant:
                self.channel.append(messages.new_signals(self.new_instant, lv["current"], self.now))

        self._maybe_digest(active)

    def _maybe_digest(self, active: list[dict]) -> None:
        if self.now.hour < DIGEST_HOUR_UTC:
            return
        d = self.st["digest"]
        week = "%d-W%02d" % self.now.isocalendar()[:2]
        today = self.now.date().isoformat()
        level = self.st["level"]["current"]
        if d.get("weekly") != week:
            kind = "weekly"
        elif level >= WATCH and d.get("daily") != today:
            kind = "daily"
        else:
            return
        d["weekly"], d["daily"] = week, today
        days = 7 if kind == "weekly" else 1
        cutoff = self.now - timedelta(days=days)
        events = [e for e in self.st["log"] if _ts(e["ts"]) >= cutoff]
        self.channel.append(messages.digest(kind, level, active, events, self.st["sources"], self.now))
