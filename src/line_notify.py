import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"
JST = ZoneInfo("Asia/Tokyo")
MAX_RETRIES = 3


def _broadcast_message(text: str) -> None:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = {
        "messages": [{"type": "text", "text": text}],
    }

    for attempt in range(MAX_RETRIES):
        resp = requests.post(LINE_API_URL, headers=headers, json=body, timeout=10)
        if resp.ok:
            return
        if attempt < MAX_RETRIES - 1:
            time.sleep(2**attempt)

    resp.raise_for_status()


def send_daily_schedule(events: list[dict]) -> None:
    now = datetime.now(JST)
    header = f"\U0001f4c5 今日の予定（{now.month}/{now.day}）"

    if not events:
        text = f"{header}\n\n予定はありません"
    else:
        lines = []
        for ev in events:
            start: datetime = ev["start"]
            end: datetime = ev["end"]
            s = start.astimezone(JST).strftime("%H:%M")
            e = end.astimezone(JST).strftime("%H:%M")
            lines.append(f"{s}-{e} {ev['subject']}")
        body = "\n".join(lines)
        text = f"{header}\n\n{body}\n\n全{len(events)}件"

    _broadcast_message(text)
