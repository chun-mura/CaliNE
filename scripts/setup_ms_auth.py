"""Microsoft 365 初回認証スクリプト.

Device Code Flow でブラウザ認証し、MSAL トークンキャッシュを JSON ファイルに保存する。
保存されたファイルの内容を GitHub Secrets の MS_TOKEN_JSON に登録する。

使い方:
    AZURE_TENANT_ID=xxx AZURE_CLIENT_ID=yyy AZURE_CLIENT_SECRET=zzz \
      python scripts/setup_ms_auth.py
"""

import json
import os
import stat
import sys

import msal

TOKEN_FILE = "ms_token_cache.json"

SCOPES = ["https://graph.microsoft.com/Calendars.Read"]


def main() -> None:
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")

    if not tenant_id or not client_id:
        print("環境変数 AZURE_TENANT_ID, AZURE_CLIENT_ID を設定してください")
        sys.exit(1)

    cache = msal.SerializableTokenCache()
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
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

        print("認証成功!")
        print(f"トークンキャッシュを {TOKEN_FILE} に保存しました（パーミッション: 600）")
        print()
        print("次のステップ:")
        print(f"  1. {TOKEN_FILE} の内容を GitHub Secrets の MS_TOKEN_JSON に登録")
        print(f"  2. 登録後、{TOKEN_FILE} を削除してください")
    else:
        print(f"認証失敗: {result.get('error', 'unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
