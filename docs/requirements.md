# CaliNE 要件定義書

## 1. プロジェクト概要

Outlookカレンダー（Microsoft 365）から当日の予定を取得し、LINE通知およびGoogleカレンダーへの反映を日次で自動実行するアプリケーション。

**プロジェクト名**: CaliNE（Calendar + LINE）

---

## 2. システム構成

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Outlook    │    │    LINE      │    │   Google     │
│  Calendar    │    │  Messaging   │    │  Calendar    │
│ (MS Graph)   │    │    API       │    │    API       │
└──────┬───────┘    └──────▲───────┘    └──────▲───────┘
       │ 取得              │ 通知              │ 同期
       ▼                   │                   │
┌──────────────────────────┴───────────────────┴──────┐
│                    CaliNE (Python)                   │
└─────────────────────────┬───────────────────────────┘
                          │ 日次実行
                   ┌──────┴───────┐
                   │GitHub Actions│
                   │ (cron 10:00) │
                   └──────────────┘
```

---

## 3. 技術スタック

| 項目 | 技術 | 選定理由 |
|------|------|----------|
| 言語 | Python 3.12+ | MS Graph / Google Calendar 両SDKが最も充実 |
| Outlook連携 | Microsoft Graph API (`msgraph-sdk` + `azure-identity`) | 公式SDK、認証統合がシンプル |
| LINE通知 | LINE Messaging API (Push Message) | LINE Notify終了済。月200通無料で個人利用に十分 |
| Googleカレンダー | Google Calendar API (`google-api-python-client` + `google-auth`) | 公式SDK、ドキュメント豊富 |
| 日次実行 | GitHub Actions (scheduled workflow) | セットアップ最小、無料、数十分の遅延許容 |
| シークレット管理 | GitHub Actions Secrets | UIから設定、ワークフロー内で参照 |

---

## 4. 機能要件

### 4.1 Outlookカレンダーからの予定取得

| 項目 | 内容 |
|------|------|
| 対象アカウント | 組織アカウント（会社のMicrosoft 365） |
| 認証方式 | OAuth2 Client Credentials Flow（組織アカウントのためデーモン実行可能） |
| APIエンドポイント | `GET /users/{userId}/calendarView?startDateTime={start}&endDateTime={end}` |
| 取得対象 | 当日 00:00:00 〜 23:59:59 (JST) の全予定 |
| 取得項目 | タイトル (`subject`)、開始時刻 (`start`)、終了時刻 (`end`) |
| タイムゾーン | Asia/Tokyo |

### 4.2 LINE通知

| 項目 | 内容 |
|------|------|
| 通知手段 | LINE Messaging API Push Message |
| 通知先 | 自分自身（ユーザーID指定） |
| 通知タイミング | 毎朝10:00（JST）に1回 |
| 通知内容 | 当日の予定一覧（タイトル・時間） |

**通知メッセージ例**:
```
📅 今日の予定（3/20）

09:00-10:00 チームミーティング
11:00-12:00 1on1
14:00-15:30 プロジェクトレビュー

全3件
```

**予定がない場合**:
```
📅 今日の予定（3/20）

予定はありません
```

### 4.3 Googleカレンダーへの同期

| 項目 | 内容 |
|------|------|
| 認証方式 | OAuth2（リフレッシュトークン保存） |
| 対象カレンダー | 専用サブカレンダー「Outlook同期」を自動作成 |
| 同期方法 | Outlookイベントごとにカスタム Event ID を生成して `events.insert` |
| 重複防止 | カスタムEvent ID方式（OutlookイベントIDをBase32hex変換）。409 Conflictで冪等性を担保 |
| 同期項目 | タイトル、開始時刻、終了時刻 |

---

## 5. 非機能要件

### 5.1 実行環境

| 項目 | 内容 |
|------|------|
| 実行基盤 | GitHub Actions (scheduled workflow) |
| 実行スケジュール | `cron: '0 1 * * *'` (UTC 01:00 = JST 10:00) |
| 遅延許容 | 数十分の遅延を許容 |
| タイムアウト | 5分 |

### 5.2 認証情報管理

| シークレット | 保存先 | 用途 |
|-------------|--------|------|
| `AZURE_TENANT_ID` | GitHub Secrets | Azure ADテナントID |
| `AZURE_CLIENT_ID` | GitHub Secrets | Azureアプリ クライアントID |
| `AZURE_CLIENT_SECRET` | GitHub Secrets | Azureアプリ クライアントシークレット |
| `MS_USER_ID` | GitHub Secrets | 対象ユーザーのID（またはUPN） |
| `LINE_CHANNEL_ACCESS_TOKEN` | GitHub Secrets | LINE Messaging APIトークン |
| `LINE_USER_ID` | GitHub Secrets | LINE通知先ユーザーID |
| `GOOGLE_CREDENTIALS_JSON` | GitHub Secrets | Google OAuth2認証情報（JSON） |
| `GOOGLE_TOKEN_JSON` | GitHub Secrets | Google OAuthリフレッシュトークン（JSON） |

### 5.3 エラーハンドリング

| 項目 | 内容 |
|------|------|
| API呼び出し失敗 | 各APIで最大3回リトライ（指数バックオフ） |
| 全体失敗時 | GitHub Actionsのステータスで検知（メール通知をGitHub設定で有効化） |
| 部分失敗 | Outlook取得成功 → LINE通知失敗の場合もGoogleカレンダー同期は実行（独立処理） |

### 5.4 コスト

| サービス | 費用 |
|----------|------|
| Microsoft Graph API | 無料 |
| LINE Messaging API | 無料（月200通以内） |
| Google Calendar API | 無料 |
| GitHub Actions | 無料（プライベートリポジトリ: 月2,000分枠内） |
| **合計** | **$0/月** |

---

## 6. ディレクトリ構成（案）

```
CaliNE/
├── .github/
│   └── workflows/
│       └── daily_sync.yml       # GitHub Actions ワークフロー
├── src/
│   ├── __init__.py
│   ├── main.py                  # エントリポイント
│   ├── outlook.py               # Outlook カレンダー取得
│   ├── line_notify.py           # LINE 通知送信
│   └── google_calendar.py       # Google カレンダー同期
├── tests/
│   ├── __init__.py
│   ├── test_outlook.py
│   ├── test_line_notify.py
│   └── test_google_calendar.py
├── docs/
│   └── requirements.md          # 本ファイル
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 7. 事前準備（ユーザー作業）

### 7.1 Azure（Outlook連携）
1. Azure Portal → Entra ID → アプリの登録 → 新規登録
2. 「サポートされるアカウントの種類」→ 「この組織のディレクトリ内のアカウントのみ」
3. APIのアクセス許可 → Microsoft Graph → アプリケーションの許可 → `Calendars.Read` を追加
4. 管理者の同意を付与
5. 証明書とシークレット → 新しいクライアントシークレットを作成
6. テナントID、クライアントID、クライアントシークレットを控える

### 7.2 LINE（通知）
1. LINE Developers → プロバイダー作成 → Messaging APIチャネル作成
2. チャネルアクセストークン（長期）を発行
3. 作成されたBotを自分で友だち追加
4. 自分のユーザーIDを確認（LINE Developersコンソールのチャネル基本設定）

### 7.3 Google（カレンダー同期）
1. Google Cloud Console → プロジェクト作成 → Calendar API 有効化
2. 認証情報 → OAuth 2.0 クライアントID作成（デスクトップアプリ）
3. ローカルで初回認証を実行し、リフレッシュトークンを取得
4. 認証情報JSONとトークンJSONをGitHub Secretsに保存

### 7.4 GitHub
1. リポジトリのSettings → Secrets and variables → Actions
2. 上記シークレットをすべて登録

---

## 8. 改訂履歴

| 日付 | 内容 |
|------|------|
| 2026-03-20 | 初版作成 |
