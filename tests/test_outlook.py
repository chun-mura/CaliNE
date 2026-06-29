"""Outlook カレンダー取得モジュールのテスト."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kiota_abstractions.api_error import APIError

from src.outlook import JST, _build_credential, get_next_day_events

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ENV_VARS = {
    "AZURE_TENANT_ID": "fake-tenant",
    "AZURE_CLIENT_ID": "fake-client",
    "AZURE_CLIENT_SECRET": "fake-secret",
    "AZURE_USER_ID": "fake-user@example.com",
}


def _make_event(subject: str, start_hour: int, end_hour: int):
    """Graph API の event オブジェクトを模倣する SimpleNamespace を返す."""
    start_dt = datetime(2026, 3, 20, start_hour, 0, 0, tzinfo=JST)
    end_dt = datetime(2026, 3, 20, end_hour, 0, 0, tzinfo=JST)
    return SimpleNamespace(
        id=f"event-{subject}",
        subject=subject,
        start=SimpleNamespace(date_time=start_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000")),
        end=SimpleNamespace(date_time=end_dt.strftime("%Y-%m-%dT%H:%M:%S.0000000")),
    )


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.outlook._build_client")
@patch("src.outlook._fetch_events", new_callable=AsyncMock)
async def test_get_next_day_events_multiple_sorted(mock_fetch, mock_build):
    """正常系: 複数の予定が時刻順にソートされて返る."""
    mock_build.return_value = MagicMock()

    # わざと時刻順をばらばらに返す
    mock_fetch.return_value = [
        {
            "id": "ev-1",
            "subject": "午後会議",
            "start": datetime(2026, 3, 20, 14, 0, tzinfo=JST),
            "end": datetime(2026, 3, 20, 15, 0, tzinfo=JST),
        },
        {
            "id": "ev-2",
            "subject": "朝会",
            "start": datetime(2026, 3, 20, 9, 0, tzinfo=JST),
            "end": datetime(2026, 3, 20, 10, 0, tzinfo=JST),
        },
        {
            "id": "ev-3",
            "subject": "ランチ",
            "start": datetime(2026, 3, 20, 12, 0, tzinfo=JST),
            "end": datetime(2026, 3, 20, 13, 0, tzinfo=JST),
        },
    ]

    events = await get_next_day_events()

    assert len(events) == 3
    assert events[0]["subject"] == "朝会"
    assert events[1]["subject"] == "ランチ"
    assert events[2]["subject"] == "午後会議"
    # 各要素にタイムゾーン付き datetime が入っていること
    for ev in events:
        assert ev["start"].tzinfo is not None
        assert ev["end"].tzinfo is not None


@pytest.mark.asyncio
@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.outlook._build_client")
@patch("src.outlook._fetch_events", new_callable=AsyncMock)
async def test_get_next_day_events_empty(mock_fetch, mock_build):
    """正常系: 予定が 0 件の場合、空リストが返る."""
    mock_build.return_value = MagicMock()
    mock_fetch.return_value = []

    events = await get_next_day_events()

    assert events == []


@pytest.mark.asyncio
@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.outlook._build_client")
@patch("src.outlook._fetch_events", new_callable=AsyncMock)
@patch("src.outlook.asyncio.sleep", new_callable=AsyncMock)  # リトライの sleep をスキップ
async def test_get_next_day_events_api_failure(mock_sleep, mock_fetch, mock_build):
    """異常系: API 呼び出しが全リトライ失敗した場合、RuntimeError が送出される."""
    mock_build.return_value = MagicMock()
    mock_fetch.side_effect = ConnectionError("network error")

    with pytest.raises(RuntimeError, match="Graph API call failed after"):
        await get_next_day_events()

    # 3 回リトライしていること
    assert mock_fetch.call_count == 3


@pytest.mark.asyncio
@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.outlook._build_client")
@patch("src.outlook._fetch_events", new_callable=AsyncMock)
async def test_get_next_day_events_401_no_retry(mock_fetch, mock_build):
    """異常系: 401 は権限不足と判断し、リトライせずに RuntimeError を送出する."""
    mock_build.return_value = MagicMock()
    mock_fetch.side_effect = APIError("Unauthorized", 401, "Unauthorized")

    with pytest.raises(RuntimeError, match="Graph API が 401"):
        await get_next_day_events()

    assert mock_fetch.call_count == 1


@patch("src.outlook.ClientAssertionCredential")
def test_build_credential_uses_oidc_on_github_actions(mock_assertion):
    """GitHub Actions 環境では ClientAssertionCredential を使用する."""
    env = {
        "AZURE_TENANT_ID": "fake-tenant",
        "AZURE_CLIENT_ID": "fake-client",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.com/token?",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "gh-token",
    }
    with patch.dict("os.environ", env, clear=True):
        _build_credential()

    mock_assertion.assert_called_once_with(
        tenant_id="fake-tenant",
        client_id="fake-client",
        func=mock_assertion.call_args.kwargs["func"],
    )


@patch("src.outlook.ClientSecretCredential")
def test_build_credential_uses_secret_locally(mock_secret):
    """ローカル環境では ClientSecretCredential を使用する."""
    with patch.dict("os.environ", ENV_VARS, clear=True):
        _build_credential()

    mock_secret.assert_called_once_with(
        tenant_id="fake-tenant",
        client_id="fake-client",
        client_secret="fake-secret",
    )


def test_build_credential_raises_without_auth():
    """認証情報がない場合は RuntimeError を送出する."""
    env = {
        "AZURE_TENANT_ID": "fake-tenant",
        "AZURE_CLIENT_ID": "fake-client",
    }
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(RuntimeError, match="Azure 認証情報がありません"):
            _build_credential()
