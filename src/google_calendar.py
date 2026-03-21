"""Google カレンダーへ Outlook 予定を同期するモジュール."""

import base64
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_NAME = "Outlook同期"
TIMEZONE = "Asia/Tokyo"


def _get_credentials() -> Credentials:
    """環境変数から OAuth2 credentials を構築し、必要に応じてリフレッシュする."""
    token_info = json.loads(os.environ["GOOGLE_TOKEN_JSON"])
    client_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

    # client_info が {"installed": {...}} or {"web": {...}} 形式の場合を考慮
    client_data = client_info.get("installed") or client_info.get("web") or client_info

    creds = Credentials(
        token=token_info.get("token"),
        refresh_token=token_info.get("refresh_token"),
        token_uri=client_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_data["client_id"],
        client_secret=client_data["client_secret"],
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def _get_or_create_calendar(service) -> str:
    """「Outlook同期」カレンダーを検索し、なければ作成して ID を返す."""
    calendars = service.calendarList().list().execute()
    for cal in calendars.get("items", []):
        if cal["summary"] == CALENDAR_NAME:
            return cal["id"]

    body = {"summary": CALENDAR_NAME, "timeZone": TIMEZONE}
    created = service.calendars().insert(body=body).execute()
    return created["id"]


def _outlook_id_to_event_id(outlook_id: str) -> str:
    """Outlook イベント ID を Google Calendar Event ID に変換する.

    base32hex エンコードして小文字化することで [a-v0-9] のみの文字列にする。
    """
    encoded = base64.b32hexencode(outlook_id.encode("utf-8")).decode("ascii")
    # パディングの '=' を除去（Google Calendar Event ID では使えない）
    event_id = encoded.rstrip("=").lower()
    return event_id[:1024]


def sync_events(events: list[dict]) -> None:
    """Outlook イベントを Google カレンダーへ同期する.

    Args:
        events: [{"subject": str, "start": datetime, "end": datetime, "id": str}, ...]
    """
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = _get_or_create_calendar(service)

    for event in events:
        event_id = _outlook_id_to_event_id(event["id"])
        body = {
            "summary": event["subject"],
            "start": {
                "dateTime": event["start"].isoformat(),
                "timeZone": TIMEZONE,
            },
            "end": {
                "dateTime": event["end"].isoformat(),
                "timeZone": TIMEZONE,
            },
        }

        try:
            service.events().insert(calendarId=calendar_id, body={**body, "id": event_id}).execute()
        except HttpError as e:
            if e.resp.status == 409:
                service.events().update(calendarId=calendar_id, eventId=event_id, body=body).execute()
            else:
                raise
