"""Microsoft 365 初回認証スクリプト.

Device Code Flow でブラウザ認証し、MSAL トークンキャッシュを JSON ファイルに保存する。
保存されたファイルの内容を GitHub Secrets の MS_TOKEN_JSON に登録する。

使い方:
    AZURE_TENANT_ID=xxx AZURE_CLIENT_ID=yyy AZURE_CLIENT_SECRET=zzz \
      python scripts/setup_ms_auth.py
"""

import os
import stat
import sys

import msal
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "ms_token_cache.json"
DOTENV_FILE = ".env"


def _update_dotenv(key: str, value: str) -> None:
    """`.env` ファイルの指定キーを更新（なければ追記）."""
    escaped = value.replace("'", "'\\''")
    new_line = f"{key}='{escaped}'"

    lines: list[str] = []
    found = False
    if os.path.exists(DOTENV_FILE):
        with open(DOTENV_FILE) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    lines.append(new_line + "\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append(new_line + "\n")

    with open(DOTENV_FILE, "w") as f:
        f.writelines(lines)


SCOPES = ["https://graph.microsoft.com/Calendars.Read"]


def main() -> None:
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")

    if not client_id:
        print("環境変数 AZURE_CLIENT_ID を設定してください")
        sys.exit(1)

    cache = msal.SerializableTokenCache()
    authority = os.environ.get(
        "AZURE_AUTHORITY",
        f"https://login.microsoftonline.com/{tenant_id}"
        if tenant_id
        else "https://login.microsoftonline.com/consumers",
    )
    app = msal.PublicClientApplication(
        client_id,
        authority=authority,
        token_cache=cache,
    )

    # Device Code Flow で認証
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print("Device Code Flow の開始に失敗しました")
        sys.exit(1)

    print(flow["message"])
    print()

    # ユーザーがブラウザで認証するのを待つ
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        token_json = cache.serialize()

        # ファイルに保存（パーミッション 600: owner のみ読み書き可能）
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as f:
            f.write(token_json)

        # .env ファイルに MS_TOKEN_JSON を書き込み（既存の値があれば置換）
        _update_dotenv("MS_TOKEN_JSON", token_json)

        print("認証成功!")
        print(f"トークンキャッシュを {TOKEN_FILE} に保存しました（パーミッション: 600）")
        print(".env の MS_TOKEN_JSON を更新しました")
        print()
        print("次のステップ:")
        print(f"  1. {TOKEN_FILE} の内容を GitHub Secrets の MS_TOKEN_JSON に登録")
        print(f"  2. 登録後、{TOKEN_FILE} を削除してください")
    else:
        print(f"認証失敗: {result.get('error', 'unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
