"""CaliNE エントリポイント - Outlook予定の取得・LINE通知・Googleカレンダー同期."""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Outlook から当日の予定を取得し、LINE 通知と Google カレンダー同期を行う."""
    from src.outlook import get_today_events

    enable_gcal = os.environ.get("ENABLE_GOOGLE_CALENDAR", "false").lower() == "true"

    # ---- 1. Outlook から予定を取得 ----
    logger.info("Outlook から当日の予定を取得します")
    try:
        events = await get_today_events()
        logger.info("予定を %d 件取得しました", len(events))
    except Exception as exc:
        logger.error("Outlook からの予定取得に失敗しました: %s", type(exc).__name__)
        sys.exit(1)

    # ---- 2. LINE 通知 / Google カレンダー同期（独立実行） ----
    line_ok = False
    gcal_ok = False

    # LINE 通知
    try:
        from src.line_notify import send_daily_schedule

        logger.info("LINE 通知を送信します")
        send_daily_schedule(events)
        logger.info("LINE 通知の送信に成功しました")
        line_ok = True
    except Exception as exc:
        logger.error("LINE 通知の送信に失敗しました: %s", type(exc).__name__)

    # Google カレンダー同期（オプション）
    if enable_gcal:
        try:
            from src.google_calendar import sync_events

            logger.info("Google カレンダーへ同期します")
            sync_events(events)
            logger.info("Google カレンダー同期に成功しました")
            gcal_ok = True
        except Exception as exc:
            logger.error("Google カレンダー同期に失敗しました: %s", type(exc).__name__)
    else:
        logger.info("Google カレンダー同期はスキップ (ENABLE_GOOGLE_CALENDAR=false)")
        gcal_ok = True

    # ---- 3. 処理結果のサマリー ----
    summary = f"処理結果: 予定取得=OK ({len(events)}件), LINE通知={'OK' if line_ok else 'NG'}"
    if enable_gcal:
        summary += f", Googleカレンダー同期={'OK' if gcal_ok else 'NG'}"
    logger.info(summary)

    if not (line_ok and gcal_ok):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
