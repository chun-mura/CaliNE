"""setup_ms_auth の _update_dotenv / ヘルパー関数のテスト."""

import json
import textwrap

import pytest

from scripts.setup_ms_auth import _multiline_open_quote, _update_dotenv


@pytest.fixture()
def dotenv_path(tmp_path, monkeypatch):
    """一時ディレクトリに .env を作成し、DOTENV_FILE をモンキーパッチする."""
    env_file = tmp_path / ".env"
    monkeypatch.setattr("scripts.setup_ms_auth.DOTENV_FILE", str(env_file))
    return env_file


class TestUpdateDotenv:
    """_update_dotenv のテスト."""

    def test_create_new_key(self, dotenv_path):
        """ファイルが存在しない場合、新規作成してキーを追記する."""
        _update_dotenv("MY_KEY", "my_value")

        content = dotenv_path.read_text()
        assert "MY_KEY=" in content
        raw = content.strip().split("=", 1)[1]
        assert json.loads(raw) == "my_value"

    def test_create_new_key_in_existing_file(self, dotenv_path):
        """既存ファイルにキーがない場合、末尾に追記する."""
        dotenv_path.write_text("OTHER_KEY=other_value\n")

        _update_dotenv("MY_KEY", "my_value")

        content = dotenv_path.read_text()
        assert "OTHER_KEY=other_value" in content
        assert "MY_KEY=" in content

    def test_replace_single_line_value(self, dotenv_path):
        """既存の単一行の値を置換する."""
        dotenv_path.write_text("MY_KEY='old_value'\n")

        _update_dotenv("MY_KEY", "new_value")

        content = dotenv_path.read_text()
        assert "old_value" not in content
        assert "MY_KEY=" in content
        raw = content.strip().split("=", 1)[1]
        assert json.loads(raw) == "new_value"

    def test_replace_single_line_unquoted(self, dotenv_path):
        """クォートなしの既存値を置換する."""
        dotenv_path.write_text("MY_KEY=old_value\n")

        _update_dotenv("MY_KEY", "new_value")

        content = dotenv_path.read_text()
        assert "old_value" not in content
        assert "MY_KEY=" in content

    def test_replace_multiline_single_quoted_value(self, dotenv_path):
        """シングルクォートで囲まれた複数行の値を置換する."""
        existing = textwrap.dedent("""\
            OTHER=keep
            MS_TOKEN_JSON='{
                "AccessToken": {
                    "test-1": "test-token"
                }
            }'
            ANOTHER=also_keep
        """)
        dotenv_path.write_text(existing)

        _update_dotenv("MS_TOKEN_JSON", '{"new": "token"}')

        content = dotenv_path.read_text()
        assert "OTHER=keep" in content
        assert "ANOTHER=also_keep" in content
        assert "AccessToken" not in content
        assert "test-token" not in content
        assert "MS_TOKEN_JSON=" in content

    def test_replace_multiline_double_quoted_value(self, dotenv_path):
        """ダブルクォートで囲まれた複数行の値を置換する."""
        existing = textwrap.dedent("""\
            MS_TOKEN_JSON="{
                key: value
            }"
            KEEP=yes
        """)
        dotenv_path.write_text(existing)

        _update_dotenv("MS_TOKEN_JSON", '{"replaced": true}')

        content = dotenv_path.read_text()
        assert "KEEP=yes" in content
        assert "MS_TOKEN_JSON=" in content
        assert "key: value" not in content

    def test_preserves_other_keys(self, dotenv_path):
        """他のキーに影響を与えない."""
        existing = textwrap.dedent("""\
            FIRST=1
            TARGET=old
            LAST=3
        """)
        dotenv_path.write_text(existing)

        _update_dotenv("TARGET", "new")

        content = dotenv_path.read_text()
        assert "FIRST=1" in content
        assert "LAST=3" in content
        assert "TARGET=old" not in content

    def test_json_value_with_special_characters(self, dotenv_path):
        """JSON に特殊文字が含まれていても正しく書き込める."""
        value = '{"token": "abc\'def", "url": "https://example.com?a=1&b=2"}'

        _update_dotenv("MY_KEY", value)

        content = dotenv_path.read_text()
        assert "MY_KEY=" in content
        line = content.strip()
        raw = line.split("=", 1)[1]
        assert json.loads(raw) == value

    def test_no_partial_key_match(self, dotenv_path):
        """キー名が前方一致する別のキーに影響しない."""
        existing = textwrap.dedent("""\
            MY_KEY_EXTENDED=should_stay
            MY_KEY=should_be_replaced
        """)
        dotenv_path.write_text(existing)

        _update_dotenv("MY_KEY", "new")

        content = dotenv_path.read_text()
        assert "MY_KEY_EXTENDED=should_stay" in content


class TestMultilineOpenQuote:
    """_multiline_open_quote のテスト."""

    def test_single_quote_multiline(self):
        assert _multiline_open_quote("'{") == "'"

    def test_double_quote_multiline(self):
        assert _multiline_open_quote('"{') == '"'

    def test_single_quote_single_line(self):
        assert _multiline_open_quote("'simple_value'") is None

    def test_double_quote_single_line(self):
        assert _multiline_open_quote('"simple_value"') is None

    def test_no_quotes(self):
        assert _multiline_open_quote("plain_value") is None

    def test_empty(self):
        assert _multiline_open_quote("") is None
