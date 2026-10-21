"""Entry point."""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from . import telegram
from .config import DRY_RUN, TELEGRAM_ADMIN_CHAT_IDS, TELEGRAM_CHAT_IDS
from .engine import Engine, load_state, save_state
from .sources import ALL_SOURCES


def main() -> None:
    p = argparse.ArgumentParser(description="Estonia early-warning monitor")
    p.add_argument("--dry-run", action="store_true", help="print messages instead of sending; do not save state")
    p.add_argument("--force", action="store_true", help="run every source regardless of its interval")
    p.add_argument("--state", default=os.getenv("STATE_FILE", "state/state.json"))
    args = p.parse_args()
    dry = args.dry_run or DRY_RUN

    path = Path(args.state)
    state = load_state(path)
    engine = Engine(state, ALL_SOURCES, datetime.now(timezone.utc))
    engine.run_sources(force=args.force)
    engine.decide()

    for text in engine.channel:
        telegram.send(TELEGRAM_CHAT_IDS, text, dry, "channel")
    for text in engine.admin:
        telegram.send(TELEGRAM_ADMIN_CHAT_IDS, text, dry, "admin")

    lv = state["level"]["current"]
    print(f"Level: {lv}, active signals: {len(state['signals'])}, messages: {len(engine.channel)}")
    if dry:
        print("Dry run: state not saved")
    else:
        save_state(path, state)


if __name__ == "__main__":
    main()
