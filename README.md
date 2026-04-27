# CrowdWorks 自動応募システム Phase 1（半自動 MVP）

CrowdWorks の公開案件ページを日次スクレイピング取得し、Claude Haiku 4.5 でスコアリング、60 点以上に対して Claude Sonnet 4.6 + `crowdworks-proposal-writer` SKILL.md で応募文を生成、Google Sheets に書き込むパイプライン。応募送信はオーナーが CrowdWorks サイト上で手動実施する半自動運用。

---

## 1. ステータス

- 仕様書: `requirements/PRD.md`（v0.2, Federighi）
- フィージビリティ: `requirements/feasibility.md`（v0.2, Woz、CONDITIONAL GO）
- 実装計画: `requirements/implementation_plan.md`（v0.2, Woz、12 タスク）
- 監査: `requirements/audit_report.md`（v0.2, Rubinstein、CONDITIONAL GO）
- 実装フェーズ: Task 1 完了（プロジェクト雛形）→ Task 2 以降は `subagent-driven-development` で順次起動

---

## 2. ディレクトリ構成

```
projects/crowdworks_auto_apply/
├── README.md                       # 本ファイル
├── requirements.txt                # 依存ライブラリ（anthropic>=0.87.0 ほか）
├── .env.example                    # 環境変数テンプレート
├── .gitignore
├── pytest.ini
├── requirements/                   # 仕様・計画・監査ドキュメント
├── designs/                        # 設計成果物（必要時）
├── setup/                          # オーナー向け環境準備手順書
├── skills/
│   └── crowdworks-proposal-writer/ # 既存 SKILL.md（改変禁止、読込のみ）
├── src/                            # 実装コード（Task 2 以降で順次追加）
│   └── __init__.py
└── tests/                          # 単体テスト
    ├── __init__.py
    └── test_smoke.py
```

実装ファイルの責務分割（Task 2 以降で `src/` 配下に追加）は `requirements/implementation_plan.md` §1 File Structure を参照。

---

## 3. セットアップ

### 3.1 オーナー側準備（先行作業）

`setup/owner_setup_guide.md` の手順に従って以下を完了させる。

- Anthropic API キー取得（取得済）
- GCP Service Account 作成（Sheets API のみ）
- Google Sheets 新規作成と 4 タブ初期化
- GitHub Secrets 登録

### 3.2 ローカル開発環境

```bash
cd projects/crowdworks_auto_apply
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
pytest --version
python -c "import requests, bs4, anthropic, gspread, google.auth; print('deps ok')"
python -c "import anthropic; print('anthropic', anthropic.__version__)"
```

`anthropic 0.87.x` 以上が表示されることを確認する（audit C-1 対応）。

### 3.3 環境変数

`.env.example` を `.env` にコピーし、Anthropic API キー・Service Account パス・Spreadsheet ID を埋める。`.env` は `.gitignore` 済み。

---

## 4. 実行方法

Task 11 の GitHub Actions cron で日次自動実行（`22 0 * * *` UTC = 09:22 JST）。手動実行は GitHub Actions の `workflow_dispatch` から起動。

ローカル単発実行は Task 11 完了後に `python -m src.main` で可能になる予定。

---

## 5. CrowdWorks 利用規約遵守（最重要）

本システムは以下のハードガードを実装する。

- 応募送信は必ず人間が CrowdWorks サイト上で実施（自動送信は Phase 2 まで NO GO）
- `https://crowdworks.jp/public/` 配下の公開ページのみ取得（ログイン不要）
- 1 秒/req 以上のレート制限、1 回あたり最大 31 リクエスト
- robots.txt の Disallow を起動時にアサート（Bingbot crawl-delay 10 秒方針より厳しい設計）
- 403/429/503 / Cloudflare Challenge を検知した時点で即停止
- User-Agent に TEGG Engineering の連絡先を明示

詳細は `requirements/feasibility.md` §2 を参照。

---

## 6. 既存 SKILL.md（改変禁止）

`skills/crowdworks-proposal-writer/SKILL.md` はオーナー提供の応募文生成スキル。Task 8 で system prompt に**丸ごと注入する読込専用ファイル**として扱う。書き換えは一切禁止（CLAUDE.md 第3条／本プロジェクト方針）。

---

## 7. トラブルシュート

- `GOOGLE_SERVICE_ACCOUNT_JSON` は改行エスケープが崩れやすいため 1 行化して GitHub Secrets に格納する
- 誤って `service_account.json` を Git に commit した場合は即 Service Account 削除・再生成する
- Bot 検知（Cloudflare / CAPTCHA）が発動した場合、回避策を講じず即停止する設計（feasibility §8 R3）

---

## 8. 関連ドキュメント

- `requirements/PRD.md`: 機能要件・非機能要件
- `requirements/feasibility.md`: 技術調査・規約整合性・コスト試算
- `requirements/implementation_plan.md`: タスク分解（12 タスク）
- `requirements/audit_report.md`: Rubinstein 監査
- `setup/owner_setup_guide.md`: オーナー向け環境準備
- `skills/crowdworks-proposal-writer/SKILL.md`: 応募文生成スキル（読込専用）

---

最終更新: 2026-04-26 / バージョン: v0.2 / 担当: Woz (CTO)
