"""エントリポイントの日付解決テスト."""

from datetime import date
from unittest.mock import patch

import pytest

from src.main import resolve_target_date


def test_resolve_target_date_uses_workflow_input():
    with patch.dict("os.environ", {"TARGET_DATE": "2026-10-20"}, clear=False):
        assert resolve_target_date() == date(2026, 10, 20)


def test_resolve_target_date_rejects_invalid_input():
    with patch.dict("os.environ", {"TARGET_DATE": "20-10-2026"}, clear=False):
        with pytest.raises(ValueError, match="TARGET_DATE"):
            resolve_target_date()
