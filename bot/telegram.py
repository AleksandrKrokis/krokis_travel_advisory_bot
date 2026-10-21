"""Telegram delivery. In dry-run mode (or without a token) messages are only printed."""

from . import http
from .config import TELEGRAM_BOT_TOKEN


def send(chat_ids: list[str], text: str, dry_run: bool, label: str) -> None:
    if dry_run or not TELEGRAM_BOT_TOKEN or not chat_ids:
        print(f"\n===== [{label}] NOT SENT (dry run) =====\n{text}\n" + "=" * 40)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in chat_ids:
        r = http.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                 "disable_web_page_preview": True})
        if r.status_code == 200:
            print(f"[{label}] sent to {chat_id}")
        else:
            print(f"[{label}] Telegram error for {chat_id}: {r.text}")
