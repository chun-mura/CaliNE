"""Outlook カレンダーから当日の予定を取得するモジュール.

認証: OAuth2 Authorization Code Flow（委任権限）
初回はブラウザでサインインしてリフレッシュトークンを取得。
以降はリフレッシュトークンで自動更新。
"""

import asyncio
import os
import re
import time  # used in _StaticTokenCredential
from datetime import datetime, timedelta, timezone

from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
from msgraph.generated.users.item.calendar_view.calendar_view_request_builder import (
    CalendarViewRequestBuilder,
)

JST = timezone(timedelta(hours=9))

MAX_RETRIES = 3

# 委任権限のスコープ
SCOPES = ["Calendars.Read"]

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _build_client() -> GraphServiceClient:
    """Graph API クライアントを生成する（委任権限）."""
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    # トークンキャッシュの読み込み:
    #   ローカル: ms_token_cache.json ファイルから読み込み
    #   GitHub Actions: 環境変数 MS_TOKEN_JSON から読み込み
    token_cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ms_token_cache.json")
    ms_token_json = ""
    if os.path.exists(token_cache_file):
        with open(token_cache_file) as f:
            ms_token_json = f.read()
    else:
        ms_token_json = os.environ.get("MS_TOKEN_JSON", "")

    if ms_token_json:
        import msal

        cache = msal.SerializableTokenCache()
        cache.deserialize(ms_token_json)
        authority = os.environ.get(
            "AZURE_AUTHORITY",
            f"https://login.microsoftonline.com/{tenant_id}",
        )
        app = msal.PublicClientApplication(
            client_id,
            authority=authority,
            token_cache=cache,
        )
        graph_scopes = ["https://graph.microsoft.com/Calendars.Read"]
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError("No accounts found in token cache. Re-run setup_ms_auth.py")

        account = accounts[0]
        result = app.acquire_token_silent(graph_scopes, account=account)
        # /common authority ではキャッシュの realm と一致せず None になる場合がある。
        # アカウントの realm（テナントID）で再試行する。
        if not result and account.get("realm"):
            tenant_authority = f"https://login.microsoftonline.com/{account['realm']}"
            app_tenant = msal.PublicClientApplication(
                client_id,
                authority=tenant_authority,
                token_cache=cache,
            )
            tenant_accounts = app_tenant.get_accounts()
            if tenant_accounts:
                result = app_tenant.acquire_token_silent(graph_scopes, account=tenant_accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError(
                f"Failed to acquire token: {result.get('error_description', 'unknown') if result else 'no result'}"
            )

        # ローカル実行時: 更新されたキャッシュをファイルに書き戻す
        if os.path.exists(token_cache_file) and cache.has_state_changed:
            with open(token_cache_file, "w") as f:
                f.write(cache.serialize())

        from azure.core.credentials import AccessToken, TokenCredential

        class _StaticTokenCredential(TokenCredential):
            def __init__(self, token: str, expires_in: int):
                self._token = token
                self._expires_on = int(time.time()) + expires_in

            def get_token(self, *scopes, **kwargs) -> AccessToken:
                return AccessToken(self._token, self._expires_on)

        credential = _StaticTokenCredential(
            result["access_token"],
            result.get("expires_in", 3600),
        )
    else:
        # リフレッシュトークンがない場合: Device Code Flow（初回認証用）
        credential = DeviceCodeCredential(
            tenant_id=tenant_id,
            client_id=client_id,
        )

    client = GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])
    # httpx が base_url に末尾スラッシュを付加するため、URL テンプレート展開時に
    # "https://graph.microsoft.com/v1.0//me/..." のような二重スラッシュが生じる。
    # これを除去して正しい URL が生成されるようにする。
    client.request_adapter.base_url = client.request_adapter.base_url.rstrip("/")
    return client


async def _fetch_events(client: GraphServiceClient, start: str, end: str) -> list[dict]:
    """calendarView エンドポイントから予定を取得する（/me を使用）."""
    query_params = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetQueryParameters(
        start_date_time=start,
        end_date_time=end,
        select=["id", "subject", "start", "end"],
        orderby=["start/dateTime asc"],
    )
    request_config = CalendarViewRequestBuilder.CalendarViewRequestBuilderGetRequestConfiguration(
        query_parameters=query_params,
    )
    request_config.headers.add("Prefer", 'outlook.timezone="Asia/Tokyo"')

    result = await client.me.calendar_view.get(
        request_configuration=request_config,
    )

    events: list[dict] = []
    if result and result.value:
        for event in result.value:
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

    tomorrow = datetime.now(JST) + timedelta(days=1)
    start_of_day = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)

    start_iso = start_of_day.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_of_day.strftime("%Y-%m-%dT%H:%M:%S")

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            events = await _fetch_events(client, start_iso, end_iso)
            events.sort(key=lambda e: e["start"])
            return events
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

    raise RuntimeError(f"Graph API call failed after {MAX_RETRIES} retries") from last_exc
