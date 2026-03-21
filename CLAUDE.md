# CLAUDE.md

## セキュリティルール

以下のファイルは機密情報を含むため、絶対に読み込まないこと:

- `.env` — API キー、トークン、シークレット
- `ms_token_cache.json` — Microsoft 認証トークンキャッシュ
- `*.pem` — 証明書・秘密鍵
- `*credentials*` / `*secret*` — 認証情報全般

設定変更が必要な場合は `.env.template` を参照すること。
