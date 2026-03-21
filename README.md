# CaliNE

Outlook カレンダーの当日の予定を毎朝取得し、LINE に通知するアプリ。
Google カレンダーへの同期はオプション機能として提供。

GitHub Actions で毎朝 JST 10:00 に自動実行。

## セットアップ

### 1. Azure Portal（Microsoft 365）

> **個人の Azure アカウント** でアプリ登録を行ってください。企業の Azure AD テナントではなく、個人サブスクリプション（または無料の Azure AD テナント）で作成することを推奨します。

1. [Azure Portal](https://portal.azure.com/) > アプリの登録 > 新規登録
   - 「サポートされているアカウントの種類」は **「任意の組織ディレクトリ内のアカウントと個人の Microsoft アカウント」** を選択
2. リダイレクト URI: プラットフォームは **「Web」** を選択し、`https://login.microsoftonline.com/common/oauth2/nativeclient` を設定
3. 認証 > **「パブリック クライアント フローを許可する」** を **「はい」** に変更して保存
4. API のアクセス許可 > Microsoft Graph > **委任されたアクセス許可** > `Calendars.Read` を追加
5. 証明書とシークレット > クライアントシークレットを作成
6. 以下を`.env` に設定:
   - `AZURE_TENANT_ID`（テナント ID）
   - `AZURE_CLIENT_ID`（アプリケーション ID）
   - `AZURE_CLIENT_SECRET`（クライアントシークレットの値）
   - `AZURE_AUTHORITY`（認証サーバーの URL。個人 Microsoft アカウントを含む場合は `https://login.microsoftonline.com/common`、組織アカウントのみの場合は `https://login.microsoftonline.com/{テナントID}`）

> **既存のアプリ登録を変更する場合:**
> 「サポートされているアカウントの種類」を後から変更しようとすると `Property api.requestedAccessTokenVersion is invalid` エラーになることがあります。
> その場合は **マニフェスト** を開き、先に `"accessTokenAcceptedVersion": null` を `2` に変更して保存してから、`"signInAudience"` を `"AzureADandPersonalMicrosoftAccount"` に変更してください。

### 2. 初回 Microsoft 認証

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

source .env
AZURE_TENANT_ID=$AZURE_TENANT_ID AZURE_CLIENT_ID=$AZURE_CLIENT_ID AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET \
  python3 scripts/setup_ms_auth.py
```

表示された URL にブラウザでアクセスし、コードを入力してサインイン。
**サインインには企業用（組織）の Microsoft アカウントを使用してください。** 予定を取得する対象のカレンダーがこのアカウントに紐づきます。

出力された JSON を GitHub Secrets の `MS_TOKEN_JSON` に登録する。

既に `ms_token_cache.json` がある場合は、認証なしで `.env` に反映できる:

```bash
python3 scripts/setup_ms_auth.py --sync-env
```

> リフレッシュトークンは90日間有効（使用するたびにリセット）。
> 毎日実行していれば期限切れにはなりませんが、長期間停止した場合は再実行が必要です。

### 3. LINE Messaging API

1. [LINE公式アカウントを作成](https://entry.line.biz/) し、LINE Official Account Manager で Messaging API を有効化
2. `LINE_CHANNEL_ACCESS_TOKEN` の取得:
   - [LINE Developers](https://developers.line.biz/) > 該当チャネル > **Messaging API設定** タブ
   - 「チャネルアクセストークン（長期）」の **発行** ボタンをクリック
3. `LINE_USER_ID` の取得:
   - 同チャネルの **チャネル基本設定** タブ > 「あなたのユーザーID」に表示される `U` から始まる文字列

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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 環境変数を .env に設定してから:
python3 -m src.main
```

## テスト

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests/ -v
```

## Google カレンダー同期（オプション）

デフォルトは無効。有効にするには:

1. workflow の `ENABLE_GOOGLE_CALENDAR` を `"true"` に変更
2. GCP で Google Calendar API を有効化し、OAuth クライアント ID を作成
   - プラットフォームは **「Web」** を選択し、リダイレクト URI に `http://localhost` を設定
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
