# CaliNE

Outlook カレンダーの翌日の予定を取得し、LINE に通知するアプリ。
Google カレンダーへの同期はオプション機能として提供。

Cloudflare Cron Triggers から GitHub Actions を起動し、日〜木の JST 20:00 に自動実行。

## セットアップ

### 1. Azure Portal（Microsoft 365）

> **Client Credentials Flow（アプリケーション権限）** を使用します。ユーザーのサインインやトークン更新は不要です。
> GitHub Actions では **OIDC（Federated Identity Credentials）** で認証するため、クライアントシークレットの更新は不要です。

1. [Azure Portal](https://portal.azure.com/) > Microsoft Entra ID > アプリの登録 > 新規登録
   - 「サポートされているアカウントの種類」は **「この組織ディレクトリのみに含まれるアカウント」** を選択
2. API のアクセス許可 > アクセス許可の追加 > Microsoft Graph > **アプリケーションの許可** > `Calendars.Read` を追加
3. **管理者の同意を付与**（「○○ に管理者の同意が付与されました」と表示されること）
4. 証明書とシークレット > **フェデレーション資格情報** を追加
   - シナリオ: **GitHub Actions で Azure リソースにデプロイする**
   - Organization: GitHub のユーザー名または Organization 名
   - Repository: `CaliNE`（リポジトリ名）
   - Entity type: **Environment**
   - GitHub environment name: `production`（`daily_sync.yml` の `environment` と一致させる）
   - 名前: 任意（例: `github-actions-production`）
5. 以下を GitHub Secrets に登録:
   - `AZURE_TENANT_ID`（テナント ID）
   - `AZURE_CLIENT_ID`（アプリケーション ID）
   - `AZURE_USER_ID`（予定を取得するユーザーの UPN またはオブジェクト ID。例: `user@company.com`）

> **ローカル実行時のみ:** 証明書とシークレット > クライアントシークレットを作成し、`.env` の `AZURE_CLIENT_SECRET` に設定してください。

> **401 Unauthorized が出る場合:**
> - `Calendars.Read` が **委任された権限** になっていないか確認（**アプリケーションの許可** が必要）
> - 管理者の同意が付与されているか確認
> - `AZURE_USER_ID` がアプリ登録と同じテナント内のユーザーか確認

### 2. LINE Messaging API

1. [LINE公式アカウントを作成](https://entry.line.biz/) し、LINE Official Account Manager で Messaging API を有効化
2. `LINE_CHANNEL_ACCESS_TOKEN` の取得:
   - [LINE Developers](https://developers.line.biz/) > 該当チャネル > **Messaging API設定** タブ
   - 「チャネルアクセストークン（長期）」の **発行** ボタンをクリック
3. Bot を友だち追加したユーザー全員にメッセージが配信されます（Broadcast API）

### 3. GitHub Secrets

リポジトリの Settings > Secrets and variables > Actions に以下を登録:

| Secret | 必須 | 説明 |
|---|---|---|
| `AZURE_TENANT_ID` | Yes | Azure AD テナント ID |
| `AZURE_CLIENT_ID` | Yes | Azure アプリケーション ID |
| `AZURE_USER_ID` | Yes | 予定取得対象ユーザーの UPN またはオブジェクト ID |
| `LINE_CHANNEL_ACCESS_TOKEN` | Yes | LINE チャネルアクセストークン |
| `GOOGLE_CREDENTIALS_JSON` | No | GCP OAuth クライアント JSON（Google連携時のみ） |
| `GOOGLE_TOKEN_JSON` | No | Google 認証トークン JSON（Google連携時のみ） |

> ローカル実行時は `.env` に `AZURE_CLIENT_SECRET` も設定してください（GitHub Secrets には不要）。

### 4. Cloudflare Cron Trigger

GitHub Actions の `schedule` は混雑時に遅延するため、Cloudflare Worker から
`workflow_dispatch` API を呼び出します。Worker の Cron は UTC で設定しており、
`0 11 * * SUN-THU` は日〜木の JST 20:00 です。

#### 4-1. GitHub Fine-grained PATを作成

1. GitHub > Settings > Developer settings > Personal access tokens > Fine-grained tokens を開く
2. Resource owner に `chun-mura` を指定
3. Repository access は **Only select repositories** を選び、`CaliNE` のみに限定
4. Repository permissions の **Actions** を **Read and write** に設定
5. 有効期限を設定してトークンを発行し、安全な場所に一時保存

この権限はworkflow起動に必要な最小権限ですが、対象リポジトリのActions全般への
書き込みを含みます。短めの有効期限を設定し、更新日をカレンダーなどへ登録してください。
期限が来る前に新しいトークンを発行し、後述の `wrangler secret put` で更新します。

#### 4-2. Workerをデプロイ

Node.js 22以降とpnpmを使用します。安全に切り替えるため、初回作業はCronが動かない
金曜日または土曜日に行うことを推奨します。それ以外の日はJST 20:00とCron設定の
反映時間（最大15分）を避け、デプロイとSecret登録を連続して行ってください。

```bash
cd cloudflare
pnpm --version
pnpm install --frozen-lockfile
pnpm exec wrangler login
pnpm run deploy:dry-run
pnpm run deploy
pnpm exec wrangler secret put GITHUB_TOKEN
```

`pnpm --version` が失敗する場合は、Volta利用環境では
`volta install pnpm@11.3.0` を実行してから続けてください。Corepackは必須ではありません。

最後のコマンドで、4-1で発行したPATを対話形式で入力します。トークンをソースコード、
設定ファイル、コマンドライン引数へ記載しないでください。Secret登録コマンドは新しい
Workerバージョンを作成して即時デプロイします。

WorkerとSecretを確認してから、この変更をGitHubのデフォルトブランチへ反映してください。
反映によりGitHub側の古い `schedule` が削除され、Cloudflareだけが起動元になります。
切替中に旧・新の両方が起動しても、同じ通知対象日には同じLINE Retry Keyを使用するため、
LINE側で重複配信が抑止されます。

#### 4-3. 設定を確認

Cloudflare Dashboard > Workers & Pages > `caline-scheduler` で以下を確認します。

- Settings > Triggers > Cron Triggers: `0 11 * * SUN-THU`
- Settings > Variables and Secrets: `GITHUB_TOKEN` がSecretとして登録済み
- Logs / Observability: Cron実行後に `GitHub workflow dispatch accepted` が記録される
- Issues: Workerの例外検知が有効

Cron反映には最大15分かかる場合があります。次回の20:00以降、GitHub Actionsの
`Daily Calendar Sync` が `workflow_dispatch` で実行され、LINE通知が届くことを確認してください。
CloudflareのIssues画面では、検知した失敗をWebhookやチャットへ送るAutomationも設定できます。

#### 4-4. 任意のローカル疎通確認

すぐに確認する場合は `cloudflare/.dev.vars` を作成し、次の1行だけを記載します。

```dotenv
GITHUB_TOKEN="発行したPAT"
```

その後、Workerを起動します。

```bash
cd cloudflare
pnpm exec wrangler dev --test-scheduled
```

別のターミナルから次を実行すると、本物のGitHub ActionsとLINE通知が1回実行されます。
同じ通知対象日にもう一度実行した場合、LINE側で重複配信が抑止されます。

```bash
curl "http://localhost:8787/cdn-cgi/local/scheduled?cron=0+11+*+*+SUN-THU"
```

確認後は `.dev.vars` を削除してください。このファイルは `.gitignore` の対象です。

#### 4-5. 障害時の再実行とロールバック

CloudflareまたはGitHub APIの一時障害ではWorkerが最大3回試行します。GitHub Actions側で
失敗した場合は、通知対象日を指定して手動再実行できます。

```bash
gh workflow run "Daily Calendar Sync" -f target_date=2026-10-20
```

日付は実際に通知したい日（JST）へ置き換えてください。Cron起動時はCloudflareの予定実行時刻
から通知対象日を固定するため、GitHub側の開始が日付をまたいでも対象日は変わりません。

Cloudflare Cron自体を利用できない状態が続く場合は、`.github/workflows/daily_sync.yml` の
`workflow_dispatch` の前へ一時的に次の設定を戻し、デフォルトブランチへ反映します。

```yaml
  schedule:
    - cron: "17 11 * * 0-4" # 緊急用。毎時0分を避けたJST 20:17
```

復旧後はこの緊急用scheduleを再度削除してください。

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
| Microsoft | アクセストークン | 1時間 | OIDC / Client Credentials で自動取得（対応不要） |
| Google | アクセストークン | 1時間 | 自動更新（対応不要） |
| Google | リフレッシュトークン | テスト: 7日 / 本番: 無期限 | GCPを本番公開にするか、再認証 |
