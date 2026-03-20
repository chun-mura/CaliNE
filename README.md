# CaliNE

Outlook カレンダーの当日の予定を毎朝取得し、LINE に通知するアプリ。
Google カレンダーへの同期はオプション機能として提供。

GitHub Actions で毎朝 JST 10:00 に自動実行。

## セットアップ

### 1. Azure Portal（Microsoft 365）

1. [Azure Portal](https://portal.azure.com/) > アプリの登録 > 新規登録
2. リダイレクト URI: `https://login.microsoftonline.com/common/oauth2/nativeclient`
3. API のアクセス許可 > Microsoft Graph > **委任されたアクセス許可** > `Calendars.Read` を追加
4. 証明書とシークレット > クライアントシークレットを作成
5. 以下をメモ:
   - `AZURE_TENANT_ID`（テナント ID）
   - `AZURE_CLIENT_ID`（アプリケーション ID）
   - `AZURE_CLIENT_SECRET`（クライアントシークレットの値）

### 2. 初回 Microsoft 認証

```bash
pip install -r requirements.txt

AZURE_TENANT_ID=xxx AZURE_CLIENT_ID=yyy AZURE_CLIENT_SECRET=zzz \
  python scripts/setup_ms_auth.py
```

表示された URL にブラウザでアクセスし、コードを入力してサインイン。
出力された JSON を GitHub Secrets の `MS_TOKEN_JSON` に登録する。

> リフレッシュトークンは90日間有効（使用するたびにリセット）。
> 毎日実行していれば期限切れにはなりませんが、長期間停止した場合は再実行が必要です。

### 3. LINE Messaging API

1. [LINE Developers](https://developers.line.biz/) > プロバイダー作成 > チャネル作成（Messaging API）
2. チャネルアクセストークン（長期）を発行
3. 自分の LINE ユーザー ID を確認（チャネル基本設定 > あなたのユーザーID）
4. 以下をメモ:
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_USER_ID`

### 4. GitHub Secrets

リポジトリの Settings > Secrets and variables > Actions に以下を登録:

| Secret | 必須 | 説明 |
|---|---|---|
| `AZURE_TENANT_ID` | Yes | Azure AD テナント ID |
| `AZURE_CLIENT_ID` | Yes | Azure アプリケーション ID |
| `AZURE_CLIENT_SECRET` | Yes | Azure クライアントシークレット |
| `MS_TOKEN_JSON` | Yes | `setup_ms_auth.py` の出力 JSON |
| `LINE_CHANNEL_ACCESS_TOKEN` | Yes | LINE チャネルアクセストークン |
| `LINE_USER_ID` | Yes | LINE ユーザー ID |
| `GOOGLE_CREDENTIALS_JSON` | No | GCP OAuth クライアント JSON（Google連携時のみ） |
| `GOOGLE_TOKEN_JSON` | No | Google 認証トークン JSON（Google連携時のみ） |

### 5. 動作確認

GitHub Actions の `workflow_dispatch` で手動実行:

```bash
gh workflow run "Daily Calendar Sync"
```

## ローカル実行

```bash
pip install -r requirements.txt
# 環境変数を .env に設定してから:
python -m src.main
```

## テスト

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Google カレンダー同期（オプション）

デフォルトは無効。有効にするには:

1. workflow の `ENABLE_GOOGLE_CALENDAR` を `"true"` に変更
2. GCP で Google Calendar API を有効化し、OAuth クライアント ID を作成
3. 初回認証でリフレッシュトークンを取得:

```bash
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', ['https://www.googleapis.com/auth/calendar'])
creds = flow.run_local_server(port=0)
import json
print(json.dumps({'token': creds.token, 'refresh_token': creds.refresh_token}))
"
```

4. `GOOGLE_CREDENTIALS_JSON` と `GOOGLE_TOKEN_JSON` を GitHub Secrets に登録

## トークン期限

| サービス | トークン | 有効期限 | 期限切れ時の対応 |
|---|---|---|---|
| Microsoft | アクセストークン | 1時間 | 自動更新（対応不要） |
| Microsoft | リフレッシュトークン | 90日（使用でリセット） | `setup_ms_auth.py` を再実行 |
| Google | アクセストークン | 1時間 | 自動更新（対応不要） |
| Google | リフレッシュトークン | テスト: 7日 / 本番: 無期限 | GCPを本番公開にするか、再認証 |
