"""LINE 通知モジュールのテスト."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.line_notify import send_daily_schedule

JST = ZoneInfo("Asia/Tokyo")

ENV_VARS = {
    "LINE_CHANNEL_ACCESS_TOKEN": "fake-token",
}


def _make_events(*specs: tuple[str, int, int]) -> list[dict]:
    """(subject, start_hour, end_hour) のタプルから予定リストを生成する."""
    events = []
    for subject, sh, eh in specs:
        events.append(
            {
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
@patch("src.line_notify.requests.post")
@patch("src.line_notify.datetime")
def test_send_daily_schedule_with_events(mock_dt, mock_post):
    """正常系: 予定ありの場合、フォーマットされたメッセージが送信される."""
    # datetime.now(JST) を固定
    mock_dt.now.return_value = datetime(2026, 3, 20, 10, 0, tzinfo=JST)
    # side_effect で通常の datetime コンストラクタを維持
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_post.return_value = mock_resp

    events = _make_events(
        ("チームミーティング", 9, 10),
        ("1on1", 11, 12),
        ("プロジェクトレビュー", 14, 15),
    )

    send_daily_schedule(events)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    text = body["messages"][0]["text"]

    # ヘッダー確認
    assert "明日の予定（3/21）" in text
    # 各予定の時刻とタイトル確認
    assert "09:00-10:00 チームミーティング" in text
    assert "11:00-12:00 1on1" in text
    assert "14:00-15:30" not in text  # 15:00 であること
    assert "14:00-15:00 プロジェクトレビュー" in text
    # 件数フッター
    assert "全3件" in text


@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.line_notify.requests.post")
@patch("src.line_notify.datetime")
def test_send_daily_schedule_no_events(mock_dt, mock_post):
    """正常系: 予定なしの場合、「予定はありません」メッセージが送信される."""
    mock_dt.now.return_value = datetime(2026, 3, 20, 10, 0, tzinfo=JST)

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_post.return_value = mock_resp

    send_daily_schedule([])

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    text = body["messages"][0]["text"]

    assert "明日の予定（3/21）" in text
    assert "予定はありません" in text
    # 件数フッターは含まれないこと
    assert "全" not in text


@patch.dict("os.environ", ENV_VARS, clear=False)
@patch("src.line_notify.requests.post")
@patch("src.line_notify.time.sleep")  # リトライの sleep をスキップ
@patch("src.line_notify.datetime")
def test_send_daily_schedule_api_failure(mock_dt, mock_sleep, mock_post):
    """異常系: API 呼び出しが全リトライ失敗した場合、例外が送出される."""
    mock_dt.now.return_value = datetime(2026, 3, 20, 10, 0, tzinfo=JST)

    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("Internal Server Error")
    mock_post.return_value = mock_resp

    with pytest.raises(Exception, match="Internal Server Error"):
        send_daily_schedule([])

    # MAX_RETRIES (3) 回リトライしていること
    assert mock_post.call_count == 3
