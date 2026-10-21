"""Signal model shared by all sources."""

from dataclasses import dataclass, field

from .config import EVENT_TTL_DAYS


@dataclass
class Signal:
    # Stable key: the same situation must produce the same id on every run
    id: str
    # Independent-source group. Composite level counts distinct groups,
    # so many hits from one group never escalate on their own.
    group: str
    tier: int
    title: str
    detail: str = ""
    url: str = ""
    # "state": active while the source keeps reporting it
    # "event": one-off, active for ttl_days after first seen
    kind: str = "state"
    ttl_days: float = EVENT_TTL_DAYS


@dataclass
class SourceResult:
    signals: list[Signal] = field(default_factory=list)
    # Lines for the periodic digest (e.g. current Polymarket odds)
    digest: list[str] = field(default_factory=list)
