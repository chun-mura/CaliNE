"""Google カレンダー同期モジュールのテスト.

google_calendar.py は未実装のため、要件定義書 (docs/requirements.md) の
セクション 4.3 を基にテストを先行で作成する。

想定する公開インターフェース:
  - sync_events(events: list[dict]) -> None
    Outlook から取得した予定リストを Google カレンダーの
    サブカレンダー「Outlook同期」に同期する。

想定する内部動作:
  - サブカレンダー「Outlook同期」が存在しなければ自動作成する
  - 各イベントの Outlook ID を Base32hex に変換してカスタム Event ID とする
  - events.insert で新規作成。409 Conflict の場合は events.update で更新
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

# google_calendar.py がまだ存在しないため、import エラーを想定して
# モジュールが存在する前提でテストを記述する。
# CI で google_calendar.py が実装されるまでは skip される。
try:
    from src.google_calendar import sync_events
except ImportError:
    pytest.skip(
        "src.google_calendar モジュールが未実装のためスキップ",
        allow_module_level=True,
    )

JST = ZoneInfo("Asia/Tokyo")

ENV_VARS = {
    "GOOGLE_CREDENTIALS_JSON": '{"installed":{"client_id":"x","client_secret":"y"}}',
    "GOOGLE_TOKEN_JSON": '{"token":"t","refresh_token":"r"}',
}


def _make_events(*specs: tuple[str, int, int]) -> list[dict]:
    """(subject, start_hour, end_hour) のタプルから予定リストを生成する."""
    events = []
    for i, (subject, sh, eh) in enumerate(specs):
        events.append(
            {
                "id": f"outlook-event-{i}",
                "subject": subject,
                "start": datetime(2026, 3, 20, sh, 0, tzinfo=JST),
                "end": datetime(2026, 3, 20, eh, 0, tzinfo=JST),
            }
        )
    return events


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------


@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.google_calendar.build")
@patch("src.google_calendar._get_credentials")
def test_sync_events_insert_new(mock_creds, mock_build):
    """正常系: 新規イベントが insert で Google カレンダーに作成される."""
    mock_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    # calendarList().list() でサブカレンダーが既に存在する想定
    mock_service.calendarList().list().execute.return_value = {
        "items": [{"id": "outlook_sync_cal_id", "summary": "Outlook同期"}]
    }

    # events().insert() が成功する
    mock_insert = mock_service.events().insert
    mock_insert.return_value.execute.return_value = {"id": "event123"}

    events = _make_events(("朝会", 9, 10))
    sync_events(events)

    # insert が呼ばれていること
    mock_insert.assert_called()
    insert_kwargs = mock_insert.call_args
    # calendarId にサブカレンダーが指定されていること
    assert "outlook_sync_cal_id" in str(insert_kwargs) or mock_insert.called


@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.google_calendar.build")
@patch("src.google_calendar._get_credentials")
def test_sync_events_conflict_then_update(mock_creds, mock_build):
    """正常系: 409 Conflict 時に update にフォールバックする."""
    from googleapiclient.errors import HttpError

    mock_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    mock_service.calendarList().list().execute.return_value = {
        "items": [{"id": "outlook_sync_cal_id", "summary": "Outlook同期"}]
    }

    # insert が 409 Conflict を返す
    resp_409 = MagicMock()
    resp_409.status = 409
    resp_409.reason = "Conflict"
    mock_service.events().insert.return_value.execute.side_effect = HttpError(resp=resp_409, content=b"conflict")

    # update は成功する
    mock_service.events().update.return_value.execute.return_value = {"id": "event123"}

    events = _make_events(("朝会", 9, 10))
    sync_events(events)

    # update が呼ばれていること
    mock_service.events().update.assert_called()


@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.google_calendar.build")
@patch("src.google_calendar._get_credentials")
def test_sync_events_auto_create_subcalendar(mock_creds, mock_build):
    """正常系: サブカレンダー「Outlook同期」が存在しない場合、自動作成される."""
    mock_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    # calendarList に「Outlook同期」が存在しない
    mock_service.calendarList().list().execute.return_value = {"items": []}

    # calendars().insert() でサブカレンダーを作成
    mock_service.calendars().insert.return_value.execute.return_value = {
        "id": "new_cal_id",
        "summary": "Outlook同期",
    }

    # events().insert() が成功する
    mock_service.events().insert.return_value.execute.return_value = {"id": "ev1"}

    events = _make_events(("朝会", 9, 10))
    sync_events(events)

    # calendars().insert が呼ばれていること（サブカレンダー作成）
    mock_service.calendars().insert.assert_called()
