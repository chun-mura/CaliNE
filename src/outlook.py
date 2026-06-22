"""Outlook カレンダーから当日の予定を取得するモジュール.

認証: Client Credentials Flow（アプリケーション権限）
Azure AD アプリの Client Secret を使用。ユーザートークン不要。
"""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.free_busy_status import FreeBusyStatus
from msgraph.generated.models.response_type import ResponseType
from msgraph.generated.users.item.calendar_view.calendar_view_request_builder import (
    CalendarViewRequestBuilder,
)

JST = timezone(timedelta(hours=9))

MAX_RETRIES = 3

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _build_client() -> GraphServiceClient:
    """Graph API クライアントを生成する（アプリケーション権限）."""
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    client = GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])
    client.request_adapter.base_url = client.request_adapter.base_url.rstrip("/")
    return client


async def _fetch_events(client: GraphServiceClient, user_id: str, start: str, end: str) -> list[dict]:
    """calendarView エンドポイントから予定を取得する."""
    query_params = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetQueryParameters(
        start_date_time=start,
        end_date_time=end,
        select=["id", "subject", "start", "end", "isCancelled", "responseStatus", "showAs"],
        orderby=["start/dateTime asc"],
    )
    request_config = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetRequestConfiguration(
        query_parameters=query_params,
    )
    request_config.headers.add("Prefer", 'outlook.timezone="Asia/Tokyo"')

    result = await client.users.by_user_id(user_id).calendar_view.get(
        request_configuration=request_config,
    )

    events: list[dict] = []
    if result and result.value:
        for event in result.value:
            if event.is_cancelled:
                continue
            if event.response_status and event.response_status.response == ResponseType.Declined:
                continue
            if event.show_as == FreeBusyStatus.Free:
                continue
            events.append(
                {
                    "id": event.id or "",
                    "subject": _CONTROL_CHARS.sub("", event.subject or ""),
                    "start": datetime.fromisoformat(event.start.date_time).replace(tzinfo=JST),
                    "end": datetime.fromisoformat(event.end.date_time).replace(tzinfo=JST),
                }
            )
    return events


async def get_next_day_events() -> list[dict]:
    """翌日 (JST) の予定を取得して時刻順のリストで返す.

    Returns:
        [{"subject": str, "start": datetime, "end": datetime}, ...]
    """
    client = _build_client()
    user_id = os.environ["AZURE_USER_ID"]

    tomorrow = datetime.now(JST) + timedelta(days=1)
    start_of_day = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)

    start_iso = start_of_day.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_of_day.strftime("%Y-%m-%dT%H:%M:%S")

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            events = await _fetch_events(client, user_id, start_iso, end_iso)
            events.sort(key=lambda e: e["start"])
            return events
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

    raise RuntimeError(f"Graph API call failed after {MAX_RETRIES} retries") from last_exc
