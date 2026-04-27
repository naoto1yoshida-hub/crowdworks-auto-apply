# CrowdWorks 自動応募システム Phase 1（半自動 MVP）実装計画書

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**バージョン**: v0.3
**更新日**: 2026-04-27
**改訂者**: Jobs (CEO) - Woz レートリミット停止後の引継完遂分
**前版**: v0.2 (2026-04-24, Woz) / v0.1 (2026-04-21, Woz)

> **v0.3 の趣旨 (2026-04-27)**: Task 4 着手時に Woz が実機 HTML を 1 回取得して構造解析した結果、`/public/jobs?order=new` は Vue ベース SPA で `<vue-container data="...">` 属性に searchResult JSON が完全な形で埋め込まれており、v0.2 が前提とした BS4 + DOM セレクタ方式は実 HTML に対応する DOM が存在しないため原理的に成立しないことが判明。オーナー承認のもと JSON 抽出方式 (案 A) に全面切替。Task 4 セクション内の旧 BS4 セレクタ前提の Step 記述は参考扱いとし、実装は本書冒頭 §0.1 で示す JSON 抽出方式に従う。

**Goal:** CrowdWorks 公開 HTML ページ（`/public/jobs?order=new`）を requests + BeautifulSoup で日次スクレイピング取得し、Claude Haiku 4.5 でスコアリング、60 点以上の案件に対して Claude Sonnet 4.6 + `crowdworks-proposal-writer` SKILL.md を system prompt に注入した応募文を生成、Google Sheets（4 タブ構成）に直接書き込む半自動パイプラインを GitHub Actions cron（非ピッタリ時刻）で構築する。応募送信は必ずオーナーが CrowdWorks サイト上で手動実施し、Sheets 上で status を APPLIED に更新する。

**Architecture:** 単一 Python エントリポイント（`main.py`）が Fetcher → Idempotency → Scorer → Filter → ProposalGenerator → SheetsClient の順にコンポーネントを直列呼び出しする。Gmail API は採用しない。永続状態は Google Sheets 4 タブ（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`）に集約し、GitHub Actions cron（`22 0 * * *` UTC ≒ 09:22 JST、`:00` ピッタリ回避）で無人起動。冪等性は `master_jobs_raw` の `job_id` で担保し、1 日 10 件までをハードリミットとして適用する。HTML 構造変化・Bot 検知発動に備えて CSS セレクタを環境変数化し、パース失敗は `execution_log` に `selector_miss` / `blocked` / `fatal` として記録する。

**Tech Stack:**
- Python 3.11
- `requests==2.32.3`（HTTP GET、User-Agent 設定、タイムアウト制御）
- `beautifulsoup4==4.14.3`（HTML パース、2025-11-30 リリースの最新系列 [Fact: PyPI 2026-04-24]）
- `anthropic>=0.87.0`（Claude API、Haiku 4.5 スコアリング + Sonnet 4.6 SKILL.md 注入）[Fact] feasibility v0.2 §11「PyPI `anthropic` 最新系列、2026-04 時点で 0.87+」と整合（audit C-1 対応、2026-04-26）。
- `gspread==6.1.4` + `google-auth==2.35.0`（Sheets 書き込み。**Sheets API のみ**、Gmail API 不要）
- `pytest==8.3.3` + `pytest-mock==3.14.0`（テスト）
- `python-dotenv==1.0.1`（ローカル実行用）
- GitHub Actions（`ubuntu-latest`, Python 3.11、cron スケジュール `22 0 * * *`）

---

## 0. v0.1 → v0.2 変更概要（結論ファースト）

v0.1（2026-04-21）は RSS / Gemini / Gmail を前提としており、以下の理由で完全に破綻していたため全面書き直した。

| # | 変更カテゴリ | v0.1 | v0.2 | 根拠 |
|---|---|---|---|---|
| 1 | **案件取得方式** | `feedparser` による RSS パース（`https://crowdworks.jp/public/jobs.rss`） | `requests` + `beautifulsoup4` による HTML スクレイピング（`https://crowdworks.jp/public/jobs?order=new`） | [Fact] CrowdWorks 公式 RSS 配信終了・URL 404（current_focus §2.1、feasibility §1 v0.2）|
| 2 | **スコアリング LLM** | Gemini 2.5 Flash（`google-generativeai==0.8.3`） | Claude Haiku 4.5（`anthropic` SDK） | [Fact] `google-generativeai` は 2025-11-30 非推奨化済（audit C-3）、LLM プロバイダを Anthropic 単一化 |
| 3 | **応募文生成 LLM モデル ID** | `claude-sonnet-4-5-20250929` ハードコード | `claude-sonnet-4-6` を環境変数 `ANTHROPIC_SONNET_MODEL` で差替可能化 | [Fact] Anthropic 公式 API ID、audit C-2 対応 |
| 4 | **Gmail 下書き作成** | `google-api-python-client` で `drafts.create`、ドメイン委任必要 | **完全撤回**。`gmail_client.py` と `test_gmail_client.py` を削除 | [Fact] 個人 `@gmail.com` ではドメイン委任不可（audit M-3）、オーナー判断で Sheets 直書きに統一 |
| 5 | **Sheets タブ構成** | 5 タブ（`master_jobs_raw` / `draft_proposals` / `sent_log` / `execution_log` / `scoring_config`） | 4 タブ（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`）。`draft_proposals` と `sent_log` を `daily_candidates` に統合 | PRD v0.2 §7.3 F-41 / feasibility v0.2 §6 |
| 6 | **日次上限** | 5 件 | **10 件**（Jobs 決定変更。PRD v0.2 F-74） | current_focus §2.2、PRD v0.2 §4.7 |
| 7 | **cron 時刻** | `0 0 * * *` UTC（09:00 JST ピッタリ） | `22 0 * * *` UTC（09:22 JST、非ピッタリ） | [Fact] GitHub Actions は `:00` ピッタリで高遅延（audit M-4） |
| 8 | **HTML セレクタ戦略** | 該当なし（RSS だったため） | セレクタを環境変数 `SELECTOR_JOB_ITEM` / `SELECTOR_JOB_TITLE` / `SELECTOR_JOB_LINK` / `SELECTOR_JOB_POSTED_AT` / `SELECTOR_JOB_BODY` で外部注入 | [Inference] feasibility v0.2 §3.2 / §8 R1、HTML 構造変化への緩和 |
| 9 | **Rate Limiting** | 該当なし | `REQUEST_INTERVAL_SEC=1.0`（最低 1 秒/req）、`MAX_DETAIL_FETCH=30`（1 回あたり詳細最大 30 件）、403/429/503 は即停止 | [Fact] feasibility v0.2 §3.4 |
| 10 | **User-Agent** | `TEGGEngineering-CrowdWorksWatcher/0.1 (+mailto:...)` | `TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)` | feasibility v0.2 §2.3 / §3.4 |
| 11 | **robots.txt 検証タスク** | 存在せず | Task 4 で `robots.txt` を取得し `/public/` が Disallow に含まれないことを起動時アサート | feasibility v0.2 C1 / §2.1 |
| 12 | **Self-review** | Gemini/RSS/Gmail 前提の対応表 | 4 タブ構成・Claude 単一プロバイダ・規約遵守ハードガード前提に再編 | audit C-1/C-2/C-3/M-1/M-2/M-3/M-4 対応 |

**削除タスク（v0.1 → v0.2）:**
- v0.1 Task 10「Gmail 下書き作成」を完全削除
- v0.1 Task 1 の `google-generativeai`, `google-api-python-client`, `feedparser` を `requirements.txt` から削除
- v0.1 Task 4 の `feedparser` を用いた RSS パースを削除

**新規追加タスク（v0.1 → v0.2）:**
- Task 4 内に `robots.txt` 取得・検証ステップを追加
- Task 4 内に HTTP 取得のレート制御・403/429/503 ハンドリング・指数バックオフを追加
- Task 4 内に一覧ページのスクレイピング + 詳細ページ巡回を追加
- Task 6（Scorer）を Anthropic SDK ベースで全面書き直し
- Task 8（ProposalGen）のモデル ID を環境変数経由で差替可能化
- Task 9（SheetsClient）を 4 タブ構成に再編
- Task 12（GitHub Actions）の cron を非ピッタリ時刻に変更

---

## 0.1. v0.2 → v0.3 変更概要（2026-04-27）

実機 HTML の構造解析結果、v0.2 が前提とした BS4 + DOM セレクタ方式は成立しないことが判明したため、**Task 4 のパース戦略を JSON 抽出方式に全面切替**した。設計大転換だが、HTTP リクエスト数・サーバ負荷・robots.txt 適合性のいずれも v0.2 と同等以下である。

| # | 変更カテゴリ | v0.2 | v0.3 | 根拠 |
|---|---|---|---|---|
| 1 | **一覧パース方式** | BS4 で `ul.search_results > li.jobs_lists` を回し `<a class="item_title">` から job_id を抽出 | `<vue-container data="...">` 属性 → `html.unescape()` → `json.loads()` → `searchResult.job_offers[]` を直接展開 | [Fact] 2026-04-27 実機取得 HTML 100,490 bytes に旧 DOM 構造はゼロヒット、代わりに 50 件分の完全な JSON が埋め込まれていた |
| 2 | **取得可能フィールド** | `job_id` / `title` / 一覧の `posted_time` / `category`（DOM テキスト）。詳細ページで `description` / `budget_text` を取得 | 一覧 1 リクエストで `id` / `title` / `description_digest`(120字) / `category_id` / `genre` / `last_released_at`(ISO8601) / `payment`(5サブタイプ) / `client` をすべて JSON で取得。詳細ページは Phase 1 では Scorer 60 点以上に限定して取得 | [Fact] 一覧 JSON 構造 |
| 3 | **`posted_at` の確定** | [Unknown] DOM テキストパース要 | [Fact] `last_released_at` が ISO8601 形式で常に存在 | feasibility v0.2 §3.3 の Unknown が解消 |
| 4 | **payment 正規化** | 詳細ページの `.job_contents_price` テキストをそのまま保持 | 5 サブタイプ (fixed_price_payment / task_payment / hourly_payment / fixed_price_writing_payment / competition_payment) を日本語ラベル + `key=value` 形式の単一文字列に正規化 (`src/fetcher.parse_payment`) | [Fact] 実機 50 件で 5 サブタイプを網羅確認 |
| 5 | **SELECTOR_* 環境変数群** | `SELECTOR_JOB_ITEM` / `SELECTOR_JOB_LINK` / `SELECTOR_JOB_TITLE` / `SELECTOR_JOB_POSTED_AT` / `SELECTOR_JOB_CATEGORY` / `SELECTOR_DETAIL_BODY` / `SELECTOR_DETAIL_BUDGET` を `.env` で外部注入 | **全削除**。JSON パスはコード側固定値 (`src/fetcher.py`) で保持。env で差替える性質ではない | `.env.example` / `src/config.py` から削除済 |
| 6 | **Phase 1 詳細ページ取得** | 全件取得想定（暗黙） | **Scorer 60 点以上のみ詳細取得**（最大 10 req/日）。一覧の `description_digest` (120 字) でスコアリング | オーナー判断 2026-04-27 |
| 7 | **テストフィクスチャ** | サンプル HTML を手書きで作成 | 実機 HTML から匿名化スクリプト (`tests/fixtures/_anonymize.py`) で生成した `tests/fixtures/list_sample.json` (50 件 + PR 系 7 件) を使用。`client.username` / `user_id` / `user_picture_url` を匿名化 | 再現性とテスト品質向上 |
| 8 | **HTTP クライアント設計** | v0.2 仕様維持 (User-Agent / リトライ / レート制限 / robots.txt) | 同上。`src/http_client.py` の `HttpClient` / `RobotsChecker` クラスとして実装 | 仕様変更なし |

**削除内容（v0.2 → v0.3）:**
- `.env.example` の `SELECTOR_JOB_*` / `SELECTOR_DETAIL_*` 7 キー
- `src/config.py` の `selector_job_item` 等 7 フィールド
- v0.2 Task 4 Step 1 のサンプル HTML フィクスチャ（実機ベースの匿名化フィクスチャに置換）

**新規ファイル（v0.3 で実装完了）:**
- `src/fetcher.py` (`extract_vue_data` / `parse_payment` / `parse_job_offer_entry` / `parse_list_html`)
- `src/http_client.py` (`HttpClient` / `RobotsChecker`)
- `tests/fixtures/_anonymize.py` + `tests/fixtures/list_sample.json`
- `tests/test_fetcher.py` (14 件) / `tests/test_http_client.py` (10 件)

**未対応（Phase 1 残課題）:**
- 詳細ページのパース仕様（Task 5 以降で確定。Scorer 60 点以上の案件のみ取得）
- `category_id` → カテゴリ名のマッピング辞書（Phase 1.5）

---

## 1. File Structure

`projects/crowdworks_auto_apply/` 配下に以下を新規作成する。既存 `skills/crowdworks-proposal-writer/SKILL.md` および `requirements/` 配下ドキュメントは改変しない（SKILL.md は Task 8 で**読込のみ**、一切改変しない）。

| パス | 責務 |
|---|---|
| `src/__init__.py` | パッケージ化（空ファイル） |
| `src/models.py` | `Job` dataclass（正規化スキーマ）と `Scored` dataclass |
| `src/config.py` | 環境変数ロード、定数（`DAILY_APPLY_LIMIT=10`, `SCORE_THRESHOLD=60`, `CROWDWORKS_LIST_URL`, `USER_AGENT`, `REQUEST_TIMEOUT=30`, `REQUEST_INTERVAL_SEC=1.0`, `MAX_DETAIL_FETCH=30`, `ANTHROPIC_HAIKU_MODEL`, `ANTHROPIC_SONNET_MODEL`, セレクタ系環境変数）の集約 |
| `src/http_client.py` | `requests.Session` ラッパ。User-Agent 設定、タイムアウト、1 秒/req レート制御、指数バックオフ、403/429/503 即停止 |
| `src/fetcher.py` | `robots.txt` 検証 → 一覧ページ取得 → BeautifulSoup パース → 詳細ページ巡回 → `Job` リスト化 |
| `src/idempotency.py` | `master_jobs_raw` タブから既知 `job_id` 集合を取得し、重複案件を除外するユーティリティ |
| `src/scorer.py` | Claude Haiku 4.5 を呼び、構造化 JSON（`total_score` / `lucrative_score` / `fit_score` / `tone_hint` / `reason` / `category_detected`）で 0-100 点を取得 |
| `src/filter.py` | スコア 60 以上かつ除外ルール（PRD v0.2 §5.3）に該当しない案件を選別、1 日 10 件上限を適用 |
| `src/proposal_gen.py` | `skills/crowdworks-proposal-writer/SKILL.md` をファイル読込し Claude Sonnet 4.6 の system prompt に**改変なしで丸ごと**注入、案件テキスト + 補助情報を user prompt として渡して応募文を生成 |
| `src/sheets_client.py` | 4 タブ（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`）への upsert/append をラップ |
| `src/main.py` | パイプライン統合。try/except で各段の失敗を `execution_log` へ記録 |
| `tests/__init__.py` | 空 |
| `tests/test_models.py` | `Job`/`Scored` dataclass の構築テスト |
| `tests/test_http_client.py` | `requests` モックでレート制御・403/429/503 ハンドリング検証 |
| `tests/test_fetcher.py` | `requests` モック + BS4 パースで一覧・詳細取得の検証 |
| `tests/test_idempotency.py` | Sheets モックで既知 job_id 取得・差分抽出検証 |
| `tests/test_scorer.py` | Anthropic SDK モックでスコア抽出検証 |
| `tests/test_filter.py` | 閾値・除外ルール・日次上限の検証 |
| `tests/test_proposal_gen.py` | SKILL.md 読込 + Anthropic クライアントモック検証 |
| `tests/test_sheets_client.py` | `gspread` モックで 4 タブへの append 挙動検証 |
| `tests/test_main.py` | main オーケストレーションの正常系 1 本 |
| `tests/fixtures/sample_list.html` | テスト用一覧ページ HTML（2〜3 案件分） |
| `tests/fixtures/sample_detail.html` | テスト用詳細ページ HTML（1 案件分） |
| `tests/fixtures/sample_robots.txt` | テスト用 robots.txt（`/public/` が Disallow に含まれない版 + 含まれる版） |
| `tests/fixtures/sample_skill.md` | テスト用 SKILL.md ミニ版 |
| `requirements.txt` | 依存ライブラリ固定バージョン（feedparser / google-generativeai / google-api-python-client は含まない） |
| `.env.example` | 必須環境変数テンプレ |
| `.gitignore` | `.env` / `__pycache__` / `service_account.json` / `credentials*.json` / `token*.json` |
| `.github/workflows/daily.yml` | cron スケジュール（`22 0 * * *` UTC）、Secrets 注入 |
| `README.md` | セットアップ手順・初回動作確認・トラブルシュート |

**既存ファイル参照（改変禁止）:**
- `projects/crowdworks_auto_apply/skills/crowdworks-proposal-writer/SKILL.md` — Task 8 で**読込のみ**、system prompt に丸ごと注入する対象。ファイル書換は一切禁止。

---

## 2. Tasks

### Task 1: プロジェクト構造セットアップ

**Files:**
- Create: `projects/crowdworks_auto_apply/src/__init__.py`
- Create: `projects/crowdworks_auto_apply/tests/__init__.py`
- Create: `projects/crowdworks_auto_apply/requirements.txt`
- Create: `projects/crowdworks_auto_apply/.env.example`
- Create: `projects/crowdworks_auto_apply/.gitignore`
- Create: `projects/crowdworks_auto_apply/pytest.ini`

- [ ] **Step 1: `src/__init__.py` と `tests/__init__.py` を空ファイルで作成**

```bash
mkdir -p projects/crowdworks_auto_apply/src
mkdir -p projects/crowdworks_auto_apply/tests/fixtures
: > projects/crowdworks_auto_apply/src/__init__.py
: > projects/crowdworks_auto_apply/tests/__init__.py
```

- [ ] **Step 2: `requirements.txt` を作成**

`projects/crowdworks_auto_apply/requirements.txt`:
```
requests==2.32.3
beautifulsoup4==4.14.3
anthropic>=0.87.0
gspread==6.1.4
google-auth==2.35.0
python-dotenv==1.0.1
pytest==8.3.3
pytest-mock==3.14.0
```

[Fact] v0.1 から削除: `feedparser==6.0.11`（RSS 撤回）、`google-generativeai==0.8.3`（Gemini 撤回）、`google-api-python-client==2.149.0`（Gmail 撤回）。

[Fact] `anthropic>=0.87.0` は feasibility v0.2 §11 [Fact] 「PyPI 2026-04 時点で 0.87+」と整合（audit C-1 解消、2026-04-26）。着手時点で `pip index versions anthropic` により最新安定版を再確認し、必要なら下限値を引き上げ、上限を `<1.0` 等で固定して再現性を担保する。Step 6 の依存検証で `print(anthropic.__version__)` を実行し 0.87 以上であることを目視確認する。

- [ ] **Step 3: `.env.example` を作成**

`projects/crowdworks_auto_apply/.env.example`:
```
# === Anthropic API（Haiku 4.5 scorer + Sonnet 4.6 proposal writer） ===
ANTHROPIC_API_KEY=sk-ant-api03-xxxx
ANTHROPIC_HAIKU_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_SONNET_MODEL=claude-sonnet-4-6

# === Google Service Account (Sheets API only、Gmail API は使わない) ===
# ローカル: ファイルパス、GitHub Actions: JSON 文字列を GOOGLE_SERVICE_ACCOUNT_JSON に格納（改行崩れ対策に 1 行化推奨）
GOOGLE_SERVICE_ACCOUNT_FILE=./service_account.json
GOOGLE_SERVICE_ACCOUNT_JSON=

# === Google Sheets ===
SPREADSHEET_ID=

# === CrowdWorks HTTP 取得設定 ===
CROWDWORKS_LIST_URL=https://crowdworks.jp/public/jobs?order=new
CROWDWORKS_DETAIL_URL_TEMPLATE=https://crowdworks.jp/public/jobs/{job_id}
CROWDWORKS_ROBOTS_URL=https://crowdworks.jp/robots.txt
USER_AGENT=TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)

# === HTTP Rate Limiting ===
REQUEST_TIMEOUT=30
REQUEST_INTERVAL_SEC=1.0
MAX_DETAIL_FETCH=30
RETRY_MAX_ATTEMPTS=2
RETRY_BACKOFF_BASE=2.0

# === HTML セレクタ（構造変化時に .env だけで差替可能化） ===
# 着手時に実機 HTML を取得し、正しいセレクタを Woz が決定してコミット
SELECTOR_JOB_ITEM=ul.search_results li.jobs_lists
SELECTOR_JOB_LINK=a.item_title
SELECTOR_JOB_TITLE=a.item_title
SELECTOR_JOB_POSTED_AT=.posted_time
SELECTOR_JOB_CATEGORY=.category
SELECTOR_DETAIL_BODY=.job_detail_description
SELECTOR_DETAIL_BUDGET=.job_contents_price

# === パイプライン制御 ===
DAILY_APPLY_LIMIT=10
SCORE_THRESHOLD=60
```

[Inference] `SELECTOR_*` のデフォルト値は Task 4 着手時に Woz が実機取得したセレクタで上書きする。上記は仮置き。

**秘密鍵運用ルール（README トラブルシュートで再掲・audit M-7 対応）:**
- `GOOGLE_SERVICE_ACCOUNT_JSON` は改行エスケープが崩れやすいため**1 行化して格納**すること
- 誤って Git に commit した場合は**即 Service Account 削除・再生成**する

- [ ] **Step 4: `.gitignore` を作成**

`projects/crowdworks_auto_apply/.gitignore`:
```
.env
.env.*
service_account.json
credentials*.json
token*.json
__pycache__/
*.pyc
.pytest_cache/
.coverage
dist/
build/
*.egg-info/
.venv/
```

- [ ] **Step 5: `pytest.ini` を作成**

`projects/crowdworks_auto_apply/pytest.ini`:
```
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

- [ ] **Step 6: 依存インストール検証**

```bash
cd projects/crowdworks_auto_apply
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest --version
python -c "import requests, bs4, anthropic, gspread, google.auth; print('deps ok')"
python -c "import anthropic; print('anthropic', anthropic.__version__)"
```

Expected:
- `pytest 8.3.3` が表示される
- `deps ok` が表示される（import エラーなし）
- `anthropic 0.87.x` 以上が表示される（audit C-1 対応、feasibility §11 [Fact] と整合）

- [ ] **Step 7: Commit**

```bash
git add projects/crowdworks_auto_apply/src/__init__.py \
        projects/crowdworks_auto_apply/tests/__init__.py \
        projects/crowdworks_auto_apply/requirements.txt \
        projects/crowdworks_auto_apply/.env.example \
        projects/crowdworks_auto_apply/.gitignore \
        projects/crowdworks_auto_apply/pytest.ini
git commit -m "chore(cw): scaffold v0.2 project structure with anthropic-only deps"
```

---

### Task 2: Job / Scored dataclass（`src/models.py`）

**Files:**
- Create: `projects/crowdworks_auto_apply/src/models.py`
- Test: `projects/crowdworks_auto_apply/tests/test_models.py`

- [ ] **Step 1: RED — Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime, timezone
from src.models import Job, Scored


def test_job_minimal_construction():
    job = Job(
        job_id="11911190",
        title="Python RAG 構築",
        url="https://crowdworks.jp/public/jobs/11911190",
        description="社内文書 Q&A bot を構築したい",
        budget_text="固定30万円",
        category="システム開発",
        posted_at=datetime(2026, 4, 24, 8, 30, tzinfo=timezone.utc),
        scanned_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
    )
    assert job.job_id == "11911190"
    assert job.title == "Python RAG 構築"
    assert job.budget_text == "固定30万円"


def test_job_optional_fields_default_none():
    job = Job(
        job_id="999",
        title="test",
        url="https://crowdworks.jp/public/jobs/999",
        description="test body",
        scanned_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
    )
    assert job.budget_text is None
    assert job.category is None
    assert job.posted_at is None


def test_scored_construction():
    from datetime import datetime, timezone
    job = Job(
        job_id="1", title="t", url="u", description="d",
        scanned_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )
    scored = Scored(
        job=job,
        total_score=72,
        lucrative_score=25,
        fit_score=30,
        tone_hint="提案型",
        reason="GAS 経験と一致",
        category_detected="GAS/スプレッドシート系",
    )
    assert scored.total_score == 72
    assert scored.tone_hint == "提案型"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd projects/crowdworks_auto_apply
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.models'` または `ImportError`。

- [ ] **Step 3: GREEN — Minimal implementation**

`src/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    """CrowdWorks 案件の正規化スキーマ（feasibility v0.2 §3.3）."""
    job_id: str
    title: str
    url: str
    description: str
    scanned_at: datetime
    budget_text: Optional[str] = None
    category: Optional[str] = None
    posted_at: Optional[datetime] = None


@dataclass
class Scored:
    """Scorer（Claude Haiku 4.5）の構造化出力（feasibility v0.2 §5.3）."""
    job: Job
    total_score: int
    lucrative_score: int
    fit_score: int
    tone_hint: str
    reason: str
    category_detected: str
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_models.py -v
```

Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/models.py \
        projects/crowdworks_auto_apply/tests/test_models.py
git commit -m "feat(cw): add Job/Scored dataclasses per feasibility v0.2 schema"
```

---

### Task 3: Config ローダ（`src/config.py`）

**Files:**
- Create: `projects/crowdworks_auto_apply/src/config.py`
- Test: `projects/crowdworks_auto_apply/tests/test_config.py`

- [ ] **Step 1: RED — Write the failing test**

`tests/test_config.py`:
```python
import os
from unittest.mock import patch

from src.config import Config


def test_config_loads_defaults(monkeypatch):
    # 最小必須のみ設定
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc123")
    # 他はデフォルト値を確認するため delete
    for k in [
        "DAILY_APPLY_LIMIT", "SCORE_THRESHOLD", "REQUEST_TIMEOUT",
        "REQUEST_INTERVAL_SEC", "MAX_DETAIL_FETCH",
        "ANTHROPIC_HAIKU_MODEL", "ANTHROPIC_SONNET_MODEL",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = Config.from_env()

    assert cfg.anthropic_api_key == "sk-ant-x"
    assert cfg.spreadsheet_id == "abc123"
    assert cfg.daily_apply_limit == 10
    assert cfg.score_threshold == 60
    assert cfg.request_timeout == 30
    assert cfg.request_interval_sec == 1.0
    assert cfg.max_detail_fetch == 30
    assert cfg.haiku_model == "claude-haiku-4-5-20251001"
    assert cfg.sonnet_model == "claude-sonnet-4-6"


def test_config_respects_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    monkeypatch.setenv("DAILY_APPLY_LIMIT", "5")
    monkeypatch.setenv("ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-8")

    cfg = Config.from_env()

    assert cfg.daily_apply_limit == 5
    assert cfg.sonnet_model == "claude-sonnet-4-8"


def test_config_raises_when_required_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    import pytest
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        Config.from_env()
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.config'`。

- [ ] **Step 3: GREEN — Implement**

`src/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Anthropic
    anthropic_api_key: str
    haiku_model: str
    sonnet_model: str

    # Sheets
    spreadsheet_id: str
    google_service_account_file: str
    google_service_account_json: str

    # CrowdWorks
    crowdworks_list_url: str
    crowdworks_detail_url_template: str
    crowdworks_robots_url: str
    user_agent: str

    # Rate limiting
    request_timeout: int
    request_interval_sec: float
    max_detail_fetch: int
    retry_max_attempts: int
    retry_backoff_base: float

    # Selectors
    selector_job_item: str
    selector_job_link: str
    selector_job_title: str
    selector_job_posted_at: str
    selector_job_category: str
    selector_detail_body: str
    selector_detail_budget: str

    # Pipeline
    daily_apply_limit: int
    score_threshold: int

    @classmethod
    def from_env(cls) -> "Config":
        required = ["ANTHROPIC_API_KEY", "SPREADSHEET_ID"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"missing required env vars: {', '.join(missing)}")

        return cls(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            haiku_model=os.environ.get("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
            sonnet_model=os.environ.get("ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-6"),
            spreadsheet_id=os.environ["SPREADSHEET_ID"],
            google_service_account_file=os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "./service_account.json"),
            google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            crowdworks_list_url=os.environ.get("CROWDWORKS_LIST_URL", "https://crowdworks.jp/public/jobs?order=new"),
            crowdworks_detail_url_template=os.environ.get(
                "CROWDWORKS_DETAIL_URL_TEMPLATE", "https://crowdworks.jp/public/jobs/{job_id}"
            ),
            crowdworks_robots_url=os.environ.get("CROWDWORKS_ROBOTS_URL", "https://crowdworks.jp/robots.txt"),
            user_agent=os.environ.get(
                "USER_AGENT",
                "TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)",
            ),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
            request_interval_sec=float(os.environ.get("REQUEST_INTERVAL_SEC", "1.0")),
            max_detail_fetch=int(os.environ.get("MAX_DETAIL_FETCH", "30")),
            retry_max_attempts=int(os.environ.get("RETRY_MAX_ATTEMPTS", "2")),
            retry_backoff_base=float(os.environ.get("RETRY_BACKOFF_BASE", "2.0")),
            selector_job_item=os.environ.get("SELECTOR_JOB_ITEM", "ul.search_results li.jobs_lists"),
            selector_job_link=os.environ.get("SELECTOR_JOB_LINK", "a.item_title"),
            selector_job_title=os.environ.get("SELECTOR_JOB_TITLE", "a.item_title"),
            selector_job_posted_at=os.environ.get("SELECTOR_JOB_POSTED_AT", ".posted_time"),
            selector_job_category=os.environ.get("SELECTOR_JOB_CATEGORY", ".category"),
            selector_detail_body=os.environ.get("SELECTOR_DETAIL_BODY", ".job_detail_description"),
            selector_detail_budget=os.environ.get("SELECTOR_DETAIL_BUDGET", ".job_contents_price"),
            daily_apply_limit=int(os.environ.get("DAILY_APPLY_LIMIT", "10")),
            score_threshold=int(os.environ.get("SCORE_THRESHOLD", "60")),
        )
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/test_config.py -v
```

Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/config.py \
        projects/crowdworks_auto_apply/tests/test_config.py
git commit -m "feat(cw): add Config loader with Anthropic model IDs env-driven"
```

---

### Task 4: HTTP クライアント + Fetcher + robots.txt 検証（`src/http_client.py` / `src/fetcher.py`）

> **v0.3 注記 (2026-04-27)**: 本セクションの Step 記述は v0.2 時点の BS4 + DOM セレクタ前提で書かれている。v0.3 で **JSON 抽出方式 (vue-container[data] → json.loads) に全面切替**したため、以下の Step 内サンプルコード・サンプル HTML は **参考扱い**とし、実装は本書冒頭 §0.1 の v0.3 変更概要および `src/fetcher.py` / `src/http_client.py` の実装本体に従うこと。robots.txt 検証 / レート制限 / User-Agent 適用 / リトライ仕様は v0.2 のまま維持。

**Context:** feasibility v0.3 §3（HTTP 取得設計）および PRD v0.2 F-01〜F-07、NFR-01〜NFR-05 の実装核。v0.1 の `feedparser` ベースフェッチャー、v0.2 の BS4 セレクタ方式をいずれも撤回し、v0.3 で `requests` + `vue-container[data]` JSON 抽出方式に切替。

**Files:**
- Create: `projects/crowdworks_auto_apply/src/http_client.py`
- Create: `projects/crowdworks_auto_apply/src/fetcher.py`
- Test: `projects/crowdworks_auto_apply/tests/test_http_client.py`
- Test: `projects/crowdworks_auto_apply/tests/test_fetcher.py`
- Create: `projects/crowdworks_auto_apply/tests/fixtures/sample_list.html`
- Create: `projects/crowdworks_auto_apply/tests/fixtures/sample_detail.html`
- Create: `projects/crowdworks_auto_apply/tests/fixtures/sample_robots_ok.txt`
- Create: `projects/crowdworks_auto_apply/tests/fixtures/sample_robots_blocked.txt`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/sample_robots_ok.txt`:
```
User-agent: *
Disallow: /api/
Disallow: /admin/
Allow: /api/v3/public/

User-agent: Bingbot
Crawl-delay: 10
```

`tests/fixtures/sample_robots_blocked.txt`:
```
User-agent: *
Disallow: /public/
Disallow: /api/
```

`tests/fixtures/sample_list.html`:
```html
<!DOCTYPE html>
<html><body>
<ul class="search_results">
  <li class="jobs_lists">
    <a class="item_title" href="/public/jobs/11911190">Python で RAG チャットボット構築</a>
    <span class="posted_time">2026年4月24日 08:30</span>
    <span class="category">システム開発</span>
  </li>
  <li class="jobs_lists">
    <a class="item_title" href="/public/jobs/11911191">GAS で営業リスト自動化</a>
    <span class="posted_time">2026年4月24日 07:45</span>
    <span class="category">ホームページ制作</span>
  </li>
</ul>
</body></html>
```

`tests/fixtures/sample_detail.html`:
```html
<!DOCTYPE html>
<html><body>
<div class="job_detail_description">
社内マニュアル 500 ページをベクトル検索で横断参照する RAG システムを構築してください。
Python + LangChain + Chroma を想定。納期 2 ヶ月。
</div>
<div class="job_contents_price">固定報酬 30 万円</div>
</body></html>
```

- [ ] **Step 2: RED — http_client test**

`tests/test_http_client.py`:
```python
import time
import pytest
import requests
from unittest.mock import MagicMock

from src.http_client import RateLimitedClient, BlockedError


def _resp(status: int, text: str = "") -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def test_rate_limit_enforces_interval(mocker, monkeypatch):
    session = MagicMock()
    session.get.side_effect = [_resp(200, "a"), _resp(200, "b")]

    sleep_calls = []
    monkeypatch.setattr("src.http_client.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("src.http_client.time.monotonic", lambda: 0)  # 常に同時刻 → 必ず sleep

    client = RateLimitedClient(
        session=session, user_agent="ua", timeout=30,
        interval_sec=1.0, max_attempts=2, backoff_base=2.0,
    )
    client.get("https://example.com/a")
    client.get("https://example.com/b")

    # 2 回目の直前で ≥1.0 秒 sleep が発生
    assert any(s >= 1.0 for s in sleep_calls)


def test_403_raises_blocked_immediately(mocker):
    session = MagicMock()
    session.get.return_value = _resp(403)

    client = RateLimitedClient(
        session=session, user_agent="ua", timeout=30,
        interval_sec=0.0, max_attempts=2, backoff_base=2.0,
    )
    with pytest.raises(BlockedError):
        client.get("https://example.com/")


def test_429_raises_blocked_immediately(mocker):
    session = MagicMock()
    session.get.return_value = _resp(429)
    client = RateLimitedClient(
        session=session, user_agent="ua", timeout=30,
        interval_sec=0.0, max_attempts=2, backoff_base=2.0,
    )
    with pytest.raises(BlockedError):
        client.get("https://example.com/")


def test_503_raises_blocked_immediately(mocker):
    session = MagicMock()
    session.get.return_value = _resp(503)
    client = RateLimitedClient(
        session=session, user_agent="ua", timeout=30,
        interval_sec=0.0, max_attempts=2, backoff_base=2.0,
    )
    with pytest.raises(BlockedError):
        client.get("https://example.com/")


def test_500_retries_then_succeeds(mocker, monkeypatch):
    session = MagicMock()
    session.get.side_effect = [_resp(500), _resp(200, "ok")]
    monkeypatch.setattr("src.http_client.time.sleep", lambda s: None)

    client = RateLimitedClient(
        session=session, user_agent="ua", timeout=30,
        interval_sec=0.0, max_attempts=2, backoff_base=2.0,
    )
    resp = client.get("https://example.com/")
    assert resp.status_code == 200
    assert session.get.call_count == 2


def test_user_agent_is_set(mocker):
    session = MagicMock()
    session.get.return_value = _resp(200, "ok")
    client = RateLimitedClient(
        session=session, user_agent="TEGG-UA", timeout=30,
        interval_sec=0.0, max_attempts=2, backoff_base=2.0,
    )
    client.get("https://example.com/")
    # headers が送信されている
    _, kwargs = session.get.call_args
    assert kwargs["headers"]["User-Agent"] == "TEGG-UA"
    assert kwargs["timeout"] == 30
```

- [ ] **Step 3: Run — FAIL expected**

```bash
pytest tests/test_http_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.http_client'`。

- [ ] **Step 4: GREEN — http_client 実装**

`src/http_client.py`:
```python
from __future__ import annotations

import time
from typing import Optional

import requests


class BlockedError(Exception):
    """403 / 429 / 503 Cloudflare Challenge 等、即停止すべき応答."""


class RateLimitedClient:
    """feasibility v0.2 §3.4 の絶対遵守事項を実装した HTTP クライアント."""

    def __init__(
        self,
        session: requests.Session,
        user_agent: str,
        timeout: int,
        interval_sec: float,
        max_attempts: int,
        backoff_base: float,
    ) -> None:
        self._session = session
        self._ua = user_agent
        self._timeout = timeout
        self._interval = interval_sec
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._last_request_at: Optional[float] = None

    def _wait_interval(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)

    def get(self, url: str) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_attempts + 1):
            self._wait_interval()
            try:
                resp = self._session.get(
                    url,
                    headers={"User-Agent": self._ua, "Accept-Language": "ja,en-US;q=0.7"},
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self._max_attempts:
                    time.sleep(self._backoff_base ** attempt)
                    continue
                raise
            finally:
                self._last_request_at = time.monotonic()

            if resp.status_code in (403, 429, 503):
                # feasibility v0.2 §3.4 Retry 禁止条件: 即停止
                raise BlockedError(f"blocked with status {resp.status_code} on {url}")
            if 500 <= resp.status_code < 600:
                last_exc = requests.HTTPError(f"server error {resp.status_code}")
                if attempt < self._max_attempts:
                    time.sleep(self._backoff_base ** attempt)
                    continue
                raise last_exc
            resp.raise_for_status()
            return resp
        # 到達不可だが型安全のため
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_http_client.py -v
```

Expected: 6 passed。

- [ ] **Step 6: RED — fetcher test**

`tests/test_fetcher.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import Config
from src.fetcher import Fetcher, RobotsDisallowedError


FIXTURES = Path(__file__).parent / "fixtures"


def _make_config(monkeypatch) -> Config:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    return Config.from_env()


def _resp(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetcher_asserts_robots_allows_public(monkeypatch):
    cfg = _make_config(monkeypatch)
    robots_blocked = (FIXTURES / "sample_robots_blocked.txt").read_text()
    http = MagicMock()
    http.get.return_value = _resp(robots_blocked)

    fetcher = Fetcher(cfg, http)
    with pytest.raises(RobotsDisallowedError):
        fetcher.assert_robots_allows("/public/jobs")


def test_fetcher_allows_when_robots_ok(monkeypatch):
    cfg = _make_config(monkeypatch)
    robots_ok = (FIXTURES / "sample_robots_ok.txt").read_text()
    http = MagicMock()
    http.get.return_value = _resp(robots_ok)

    fetcher = Fetcher(cfg, http)
    fetcher.assert_robots_allows("/public/jobs")  # 例外出ない


def test_fetcher_parses_list_page(monkeypatch):
    cfg = _make_config(monkeypatch)
    list_html = (FIXTURES / "sample_list.html").read_text()
    http = MagicMock()
    http.get.return_value = _resp(list_html)

    fetcher = Fetcher(cfg, http)
    items = fetcher.fetch_list()
    assert len(items) == 2
    assert items[0]["job_id"] == "11911190"
    assert items[0]["title"].startswith("Python")
    assert items[0]["url"] == "https://crowdworks.jp/public/jobs/11911190"
    assert items[1]["job_id"] == "11911191"


def test_fetcher_skips_item_when_job_id_missing(monkeypatch):
    cfg = _make_config(monkeypatch)
    # href が壊れている HTML
    bad_html = """
    <ul class="search_results">
      <li class="jobs_lists">
        <a class="item_title" href="/malformed">broken</a>
      </li>
    </ul>
    """
    http = MagicMock()
    http.get.return_value = _resp(bad_html)

    fetcher = Fetcher(cfg, http)
    items = fetcher.fetch_list()
    assert items == []  # スキップ


def test_fetcher_fetches_detail_and_builds_job(monkeypatch):
    cfg = _make_config(monkeypatch)
    list_html = (FIXTURES / "sample_list.html").read_text()
    detail_html = (FIXTURES / "sample_detail.html").read_text()
    http = MagicMock()
    # 一覧→詳細→詳細 の順で返す
    http.get.side_effect = [_resp(list_html), _resp(detail_html), _resp(detail_html)]

    fetcher = Fetcher(cfg, http)
    jobs = fetcher.fetch_all()
    assert len(jobs) == 2
    assert jobs[0].job_id == "11911190"
    assert "RAG" in jobs[0].description
    assert jobs[0].budget_text == "固定報酬 30 万円"


def test_fetcher_respects_max_detail_fetch(monkeypatch):
    monkeypatch.setenv("MAX_DETAIL_FETCH", "1")
    cfg = _make_config(monkeypatch)
    list_html = (FIXTURES / "sample_list.html").read_text()
    detail_html = (FIXTURES / "sample_detail.html").read_text()
    http = MagicMock()
    http.get.side_effect = [_resp(list_html), _resp(detail_html)]

    fetcher = Fetcher(cfg, http)
    jobs = fetcher.fetch_all()
    # 1 件のみ詳細取得、もう 1 件は summary のまま
    assert len(jobs) == 1
    assert jobs[0].job_id == "11911190"
```

- [ ] **Step 7: Run — FAIL expected**

```bash
pytest tests/test_fetcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.fetcher'`。

- [ ] **Step 8: GREEN — fetcher 実装**

`src/fetcher.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.config import Config
from src.http_client import RateLimitedClient
from src.models import Job


class RobotsDisallowedError(Exception):
    """robots.txt が対象パスを Disallow にしている場合."""


class Fetcher:
    """CrowdWorks 公開 HTML 取得 + BeautifulSoup パース (feasibility v0.2 §3)."""

    def __init__(self, config: Config, http: RateLimitedClient) -> None:
        self._cfg = config
        self._http = http

    def assert_robots_allows(self, path: str) -> None:
        """robots.txt を取得し、User-agent: * で path が Disallow されていないことを確認."""
        resp = self._http.get(self._cfg.crowdworks_robots_url)
        rules = _parse_robots(resp.text, "*")
        for disallow in rules["disallow"]:
            if disallow and path.startswith(disallow):
                raise RobotsDisallowedError(
                    f"{path} is disallowed by robots.txt rule: Disallow: {disallow}"
                )

    def fetch_list(self) -> List[dict]:
        """一覧ページを取得し、job_id / title / url / posted_at / category を抽出."""
        resp = self._http.get(self._cfg.crowdworks_list_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(self._cfg.selector_job_item)
        results: List[dict] = []
        for item in items:
            link = item.select_one(self._cfg.selector_job_link)
            if link is None:
                continue
            href = link.get("href", "")
            job_id = _extract_job_id(href)
            if job_id is None:
                continue
            title_el = item.select_one(self._cfg.selector_job_title)
            posted_el = item.select_one(self._cfg.selector_job_posted_at)
            cat_el = item.select_one(self._cfg.selector_job_category)
            results.append({
                "job_id": job_id,
                "title": (title_el.get_text(strip=True) if title_el else ""),
                "url": _absolute_url(href),
                "posted_at_text": posted_el.get_text(strip=True) if posted_el else None,
                "category": cat_el.get_text(strip=True) if cat_el else None,
            })
        return results

    def fetch_detail(self, url: str) -> dict:
        """詳細ページを取得し description / budget_text を抽出."""
        resp = self._http.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        body_el = soup.select_one(self._cfg.selector_detail_body)
        budget_el = soup.select_one(self._cfg.selector_detail_budget)
        return {
            "description": body_el.get_text("\n", strip=True) if body_el else "",
            "budget_text": budget_el.get_text(strip=True) if budget_el else None,
        }

    def fetch_all(self) -> List[Job]:
        """一覧ページ + 詳細ページ巡回で Job のリストを構築."""
        items = self.fetch_list()
        scanned_at = datetime.now(timezone.utc)
        jobs: List[Job] = []
        limit = min(len(items), self._cfg.max_detail_fetch)
        for it in items[:limit]:
            try:
                detail = self.fetch_detail(it["url"])
            except Exception:
                # 詳細取得失敗時は summary 未取得のまま保留 → Scorer 側で description 不足として低スコア化
                detail = {"description": "", "budget_text": None}
            jobs.append(Job(
                job_id=it["job_id"],
                title=it["title"],
                url=it["url"],
                description=detail["description"],
                budget_text=detail["budget_text"],
                category=it.get("category"),
                posted_at=None,  # テキストからの確実なパースは実機 HTML 確認後に対応（TODO 不可）
                scanned_at=scanned_at,
            ))
        return jobs


# --- helpers ---

_JOB_ID_RE = re.compile(r"/public/jobs/(\d+)")


def _extract_job_id(href: str) -> Optional[str]:
    m = _JOB_ID_RE.search(href or "")
    return m.group(1) if m else None


def _absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"https://crowdworks.jp{href}"


def _parse_robots(text: str, user_agent: str) -> dict:
    """簡易 robots.txt パーサ: User-agent: * のみ抽出."""
    groups: List[dict] = []
    current: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = [p.strip() for p in line.split(":", 1)]
        key_l = key.lower()
        if key_l == "user-agent":
            if current is not None:
                groups.append(current)
            current = {"user_agents": [value], "disallow": [], "allow": []}
        elif current is None:
            continue
        elif key_l == "disallow":
            current["disallow"].append(value)
        elif key_l == "allow":
            current["allow"].append(value)
    if current is not None:
        groups.append(current)
    # user_agent に一致するグループを抽出
    for g in groups:
        if user_agent in g["user_agents"]:
            return g
    return {"user_agents": [], "disallow": [], "allow": []}
```

[Inference] `posted_at` の正確なパースは着手時点の実機 HTML 確認が必要なため、v0.2 では `None` 固定とし、Scorer には `scanned_at` ベースで「鮮度」を渡す設計で妥協する。Phase 1 運用で HTML の時刻表示フォーマット確定後に改修（本計画内 TODO ではなく、運用後改修として記録）。

- [ ] **Step 9: Run — expect PASS**

```bash
pytest tests/test_fetcher.py tests/test_http_client.py -v
```

Expected: 全 passed。

- [ ] **Step 10: Commit**

```bash
git add projects/crowdworks_auto_apply/src/http_client.py \
        projects/crowdworks_auto_apply/src/fetcher.py \
        projects/crowdworks_auto_apply/tests/test_http_client.py \
        projects/crowdworks_auto_apply/tests/test_fetcher.py \
        projects/crowdworks_auto_apply/tests/fixtures/sample_list.html \
        projects/crowdworks_auto_apply/tests/fixtures/sample_detail.html \
        projects/crowdworks_auto_apply/tests/fixtures/sample_robots_ok.txt \
        projects/crowdworks_auto_apply/tests/fixtures/sample_robots_blocked.txt
git commit -m "feat(cw): replace RSS fetcher with requests+BS4 HTML scraper and robots.txt guard"
```

---

### Task 5: Idempotency — 既知 job_id 除外（`src/idempotency.py`）

**Files:**
- Create: `projects/crowdworks_auto_apply/src/idempotency.py`
- Test: `projects/crowdworks_auto_apply/tests/test_idempotency.py`

- [ ] **Step 1: RED**

`tests/test_idempotency.py`:
```python
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.idempotency import filter_new_jobs
from src.models import Job


def _job(jid: str) -> Job:
    return Job(
        job_id=jid, title=f"t{jid}", url=f"u/{jid}", description="d",
        scanned_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def test_filter_new_jobs_excludes_known_ids():
    sheets = MagicMock()
    sheets.get_known_job_ids.return_value = {"100", "200"}
    jobs = [_job("100"), _job("300"), _job("200"), _job("400")]
    new = filter_new_jobs(jobs, sheets)
    assert [j.job_id for j in new] == ["300", "400"]


def test_filter_new_jobs_no_known():
    sheets = MagicMock()
    sheets.get_known_job_ids.return_value = set()
    jobs = [_job("1"), _job("2")]
    new = filter_new_jobs(jobs, sheets)
    assert len(new) == 2
```

- [ ] **Step 2: Run — FAIL expected**

```bash
pytest tests/test_idempotency.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.idempotency'`。

- [ ] **Step 3: GREEN**

`src/idempotency.py`:
```python
from __future__ import annotations

from typing import List, Protocol, Set

from src.models import Job


class SheetsKnownJobIds(Protocol):
    def get_known_job_ids(self) -> Set[str]: ...


def filter_new_jobs(jobs: List[Job], sheets: SheetsKnownJobIds) -> List[Job]:
    """master_jobs_raw の既知 job_id を除外して新着のみ返す."""
    known = sheets.get_known_job_ids()
    return [j for j in jobs if j.job_id not in known]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_idempotency.py -v
```

Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/idempotency.py \
        projects/crowdworks_auto_apply/tests/test_idempotency.py
git commit -m "feat(cw): add idempotency filter against master_jobs_raw"
```

---

### Task 6: Scorer（Claude Haiku 4.5）`src/scorer.py`

**Context:** v0.1 の Gemini 2.5 Flash を完全破棄し、Anthropic SDK + Claude Haiku 4.5 で再実装（audit C-3 / M-1 自動解消）。構造化 JSON 出力をプロンプト内 JSON スキーマ指示で取得（feasibility v0.2 §5.3）。

**Files:**
- Create: `projects/crowdworks_auto_apply/src/scorer.py`
- Test: `projects/crowdworks_auto_apply/tests/test_scorer.py`

- [ ] **Step 1: RED**

`tests/test_scorer.py`:
```python
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.models import Job
from src.scorer import score_job


def _job() -> Job:
    return Job(
        job_id="11911190",
        title="GAS で営業リスト自動化",
        url="https://crowdworks.jp/public/jobs/11911190",
        description="Google Apps Script と Gemini API を使った営業リスト生成の自動化案件。",
        budget_text="固定 30 万円",
        category="システム開発",
        posted_at=None,
        scanned_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def _mock_message(json_payload: dict) -> MagicMock:
    msg = MagicMock()
    block = MagicMock()
    block.text = json.dumps(json_payload, ensure_ascii=False)
    msg.content = [block]
    return msg


def test_score_job_parses_structured_json(mocker):
    payload = {
        "lucrative_score": 25,
        "fit_score": 35,
        "total_score": 80,
        "tone_hint": "提案型",
        "reason": "GAS 実績と合致",
        "category_detected": "GAS/スプレッドシート系",
    }
    client = MagicMock()
    client.messages.create.return_value = _mock_message(payload)

    scored = score_job(_job(), client=client, model="claude-haiku-4-5-20251001")

    assert scored.total_score == 80
    assert scored.lucrative_score == 25
    assert scored.fit_score == 35
    assert scored.tone_hint == "提案型"
    assert scored.category_detected == "GAS/スプレッドシート系"


def test_score_job_passes_model_id(mocker):
    client = MagicMock()
    client.messages.create.return_value = _mock_message({
        "lucrative_score": 0, "fit_score": 0, "total_score": 0,
        "tone_hint": "丁寧硬め", "reason": "-", "category_detected": "低単価",
    })
    score_job(_job(), client=client, model="claude-haiku-4-5-YYYYMMDD-custom")
    called_kwargs = client.messages.create.call_args.kwargs
    assert called_kwargs["model"] == "claude-haiku-4-5-YYYYMMDD-custom"


def test_score_job_clamps_out_of_range(mocker):
    # モデルが 0-100 範囲外を返したら 0-100 にクランプ
    client = MagicMock()
    client.messages.create.return_value = _mock_message({
        "lucrative_score": 999, "fit_score": -5, "total_score": 150,
        "tone_hint": "フランク", "reason": "x", "category_detected": "y",
    })
    scored = score_job(_job(), client=client, model="m")
    assert scored.total_score == 100
    assert scored.fit_score == 0
    assert scored.lucrative_score == 100


def test_score_job_returns_zero_on_parse_failure(mocker):
    msg = MagicMock()
    block = MagicMock()
    block.text = "これは JSON ではない"
    msg.content = [block]
    client = MagicMock()
    client.messages.create.return_value = msg
    scored = score_job(_job(), client=client, model="m")
    assert scored.total_score == 0
    assert "parse" in scored.reason.lower() or "エラー" in scored.reason
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.scorer'`。

- [ ] **Step 3: GREEN**

`src/scorer.py`:
```python
from __future__ import annotations

import json
from typing import Any

from src.models import Job, Scored


SYSTEM_PROMPT = """あなたは副業案件の適合度スコアリング専門家です。吉田尚人（31歳、京都、製造業法人営業の本業を持ち、週20-30時間稼働のAIエンジニア副業）の以下実績との適合度を評価してください:

- GAS / Google Apps Script / スプレッドシート自動化（営業リスト自動作成、Antigravity 実績あり、適合度最大）
- RAG / 社内文書検索 / チャットボット（LangChain/Chroma 使用可）
- Claude API / Anthropic API 連携
- 業務効率化 / 製造業 DX / 営業 DX
- Python / Node.js / Web スクレイピング

除外・低評価:
- iOS / Android ネイティブ / Unity / ゲーム開発 → 0 点
- 継続案件で月10時間・月3000円のような明らかに割に合わない低単価 → 0 点
- 案件本文100字未満の情報不足 → 0 点

採点配分:
- lucrative_score (0-30): 単価適合度
- fit_score (0-35): 案件ジャンル適合度
- 残り最大35点で鮮度・情報充実度・技術スタック明記度を総合
- total_score は 0-100 の整数

必ず以下の JSON のみ出力してください。前置き・コードブロック・改行前後の説明は一切禁止:
{
  "lucrative_score": <0-30 の整数>,
  "fit_score": <0-35 の整数>,
  "total_score": <0-100 の整数>,
  "tone_hint": "丁寧硬め" | "フランク" | "提案型",
  "reason": "<日本語200字以内のスコア根拠>",
  "category_detected": "GAS/スプレッドシート系" | "RAG/チャットボット系" | "業務効率化" | "ライティング" | "コンサル" | "低単価" | "その他"
}
"""


def _clamp(value: Any, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def score_job(job: Job, client: Any, model: str) -> Scored:
    """Claude Haiku 4.5 を呼び、構造化 JSON で案件スコアを取得."""
    user_prompt = (
        f"【案件情報】\n"
        f"タイトル: {job.title}\n"
        f"カテゴリ: {job.category or '未取得'}\n"
        f"予算表記: {job.budget_text or '未取得'}\n"
        f"本文:\n{job.description or '(本文未取得)'}\n"
    )
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text.strip() if response.content else ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return Scored(
            job=job,
            total_score=0,
            lucrative_score=0,
            fit_score=0,
            tone_hint="丁寧硬め",
            reason=f"parse_error: Haiku 応答が JSON ではない ({raw[:80]!r})",
            category_detected="その他",
        )

    return Scored(
        job=job,
        total_score=_clamp(data.get("total_score"), 0, 100),
        lucrative_score=_clamp(data.get("lucrative_score"), 0, 100),
        fit_score=_clamp(data.get("fit_score"), 0, 100),
        tone_hint=str(data.get("tone_hint") or "丁寧硬め"),
        reason=str(data.get("reason") or "-")[:400],
        category_detected=str(data.get("category_detected") or "その他"),
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_scorer.py -v
```

Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/scorer.py \
        projects/crowdworks_auto_apply/tests/test_scorer.py
git commit -m "feat(cw): replace Gemini scorer with Claude Haiku 4.5 structured JSON"
```

---

### Task 7: Filter（閾値・除外ルール・日次上限）`src/filter.py`

**Files:**
- Create: `projects/crowdworks_auto_apply/src/filter.py`
- Test: `projects/crowdworks_auto_apply/tests/test_filter.py`

- [ ] **Step 1: RED**

`tests/test_filter.py`:
```python
from datetime import datetime, timezone

from src.filter import select_candidates
from src.models import Job, Scored


def _scored(score: int, title: str = "t", body: str = "x" * 200) -> Scored:
    job = Job(
        job_id=title, title=title, url=f"u/{title}", description=body,
        scanned_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )
    return Scored(
        job=job, total_score=score, lucrative_score=0, fit_score=0,
        tone_hint="丁寧硬め", reason="-", category_detected="その他",
    )


def test_select_candidates_applies_threshold():
    scored = [_scored(59), _scored(60), _scored(80)]
    kept = select_candidates(scored, threshold=60, daily_limit=10)
    assert [s.total_score for s in kept] == [80, 60]  # score desc


def test_select_candidates_applies_daily_limit():
    scored = [_scored(90), _scored(85), _scored(80), _scored(70)]
    kept = select_candidates(scored, threshold=60, daily_limit=2)
    assert [s.total_score for s in kept] == [90, 85]


def test_excludes_ios_in_title():
    s = _scored(95, title="iOS ネイティブアプリ開発")
    kept = select_candidates([s], threshold=60, daily_limit=10)
    assert kept == []


def test_excludes_unity_as_word_not_substring():
    # "community" では除外されないこと（audit M-6 対応）
    s_ok = _scored(95, title="community チャットbot", body="RAG 案件 " + "x" * 200)
    kept = select_candidates([s_ok], threshold=60, daily_limit=10)
    assert len(kept) == 1

    s_ng = _scored(95, title="Unity 2D ゲーム制作", body="x" * 200)
    kept = select_candidates([s_ng], threshold=60, daily_limit=10)
    assert kept == []


def test_excludes_short_description():
    s = _scored(95, body="短い")  # 100 字未満
    kept = select_candidates([s], threshold=60, daily_limit=10)
    assert kept == []


def test_excludes_off_platform_solicitation():
    s = _scored(95, body="LINEでやり取りしましょう。CrowdWorks 外で直接契約したいです。" + "x" * 200)
    kept = select_candidates([s], threshold=60, daily_limit=10)
    assert kept == []
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_filter.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.filter'`。

- [ ] **Step 3: GREEN**

`src/filter.py`:
```python
from __future__ import annotations

import re
from typing import List

from src.models import Scored


# audit M-6 対応: 単語境界付き正規表現、タイトル限定 vs 本文全体の分離
_TITLE_EXCLUDE_PATTERNS = [
    re.compile(r"\biOS\b", re.IGNORECASE),
    re.compile(r"\bAndroid\s*ネイティブ", re.IGNORECASE),
    re.compile(r"\bUnity\b", re.IGNORECASE),
    re.compile(r"\bKotlin\b", re.IGNORECASE),
    re.compile(r"(ゲーム|動画編集|3D モデリング)"),
]

_BODY_EXCLUDE_PATTERNS = [
    re.compile(r"CrowdWorks\s*外", re.IGNORECASE),
    re.compile(r"LINE\s*で\s*やり取り"),
    re.compile(r"直接\s*契約"),
]

_MIN_DESCRIPTION_LEN = 100


def _is_excluded(s: Scored) -> bool:
    title = s.job.title or ""
    body = s.job.description or ""
    if len(body) < _MIN_DESCRIPTION_LEN:
        return True
    for p in _TITLE_EXCLUDE_PATTERNS:
        if p.search(title):
            return True
    for p in _BODY_EXCLUDE_PATTERNS:
        if p.search(body):
            return True
    return False


def select_candidates(scored: List[Scored], threshold: int, daily_limit: int) -> List[Scored]:
    """閾値以上 かつ 除外ルール非該当 を score 降順で daily_limit まで返す."""
    filtered = [s for s in scored if s.total_score >= threshold and not _is_excluded(s)]
    filtered.sort(key=lambda s: s.total_score, reverse=True)
    return filtered[:daily_limit]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_filter.py -v
```

Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/filter.py \
        projects/crowdworks_auto_apply/tests/test_filter.py
git commit -m "feat(cw): add threshold+regex exclude filter with daily limit 10"
```

---

### Task 8: ProposalGen（Claude Sonnet 4.6 + SKILL.md 注入）`src/proposal_gen.py`

**Context:** feasibility v0.2 §5.4 に従い、`skills/crowdworks-proposal-writer/SKILL.md` を**改変なしで丸ごと** Claude Sonnet 4.6 の `system` パラメータに注入する。モデル ID は環境変数経由で差替可能（audit C-2 対応）。

**Files:**
- Create: `projects/crowdworks_auto_apply/src/proposal_gen.py`
- Test: `projects/crowdworks_auto_apply/tests/test_proposal_gen.py`
- Create: `projects/crowdworks_auto_apply/tests/fixtures/sample_skill.md`

- [ ] **Step 1: Create fixture**

`tests/fixtures/sample_skill.md`:
```
---
name: crowdworks-proposal-writer-test
description: テスト用の最小 SKILL.md
---

# 応募文ルール（テスト）
名前: 吉田
稼働: 週20-30時間
絶対ルール: 嘘を書かない。
```

- [ ] **Step 2: RED**

`tests/test_proposal_gen.py`:
```python
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.models import Job, Scored
from src.proposal_gen import generate_proposal, load_skill_markdown


FIXTURES = Path(__file__).parent / "fixtures"


def _scored() -> Scored:
    job = Job(
        job_id="1", title="GAS RAG", url="u", description="GAS 案件 " + "x" * 200,
        scanned_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )
    return Scored(
        job=job, total_score=80, lucrative_score=20, fit_score=30,
        tone_hint="提案型", reason="-", category_detected="GAS/スプレッドシート系",
    )


def _mock_message(text: str):
    msg = MagicMock()
    block = MagicMock()
    block.text = text
    msg.content = [block]
    return msg


def test_load_skill_markdown_reads_real_skill_file():
    # 実在 SKILL.md は改変せず読込のみ
    skill_path = Path(__file__).resolve().parents[1] / "skills" / "crowdworks-proposal-writer" / "SKILL.md"
    text = load_skill_markdown(skill_path)
    assert "crowdworks-proposal-writer" in text
    assert "吉田" in text


def test_generate_proposal_injects_skill_into_system_prompt(mocker):
    skill_md = (FIXTURES / "sample_skill.md").read_text(encoding="utf-8")
    client = MagicMock()
    client.messages.create.return_value = _mock_message("応募文テスト本文")

    text = generate_proposal(
        _scored(),
        skill_markdown=skill_md,
        client=client,
        model="claude-sonnet-4-6",
        max_tokens=2048,
    )

    assert text == "応募文テスト本文"
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["system"] == skill_md  # 改変なし・丸ごと注入
    assert kwargs["max_tokens"] == 2048
    # user prompt にトーン・案件情報が含まれる
    user = kwargs["messages"][0]["content"]
    assert "提案型" in user
    assert "GAS RAG" in user


def test_generate_proposal_supports_model_env_override(mocker):
    skill_md = "skill"
    client = MagicMock()
    client.messages.create.return_value = _mock_message("ok")
    generate_proposal(_scored(), skill_markdown=skill_md, client=client,
                      model="claude-sonnet-4-8-20270101", max_tokens=2048)
    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-8-20270101"
```

- [ ] **Step 3: Run — FAIL**

```bash
pytest tests/test_proposal_gen.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.proposal_gen'`。

- [ ] **Step 4: GREEN**

`src/proposal_gen.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.models import Scored


def load_skill_markdown(path: Path) -> str:
    """SKILL.md を改変せず UTF-8 で読み込む（第3条: ファイル書換禁止）."""
    return path.read_text(encoding="utf-8")


def generate_proposal(
    scored: Scored,
    skill_markdown: str,
    client: Any,
    model: str,
    max_tokens: int = 2048,
) -> str:
    """Claude Sonnet 4.6 で応募文生成. system には SKILL.md を丸ごと注入."""
    job = scored.job
    user_content = (
        f"【補助情報（Scorer→ProposalGen）】\n"
        f"推定トーン: {scored.tone_hint}\n"
        f"案件タイプ: {scored.category_detected}\n"
        f"予算: {job.budget_text or '未取得'}\n"
        f"\n"
        f"【案件情報】\n"
        f"タイトル: {job.title}\n"
        f"カテゴリ: {job.category or '未取得'}\n"
        f"本文:\n{job.description}\n"
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=skill_markdown,  # 改変なしで丸ごと注入
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text if response.content else ""
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_proposal_gen.py -v
```

Expected: 3 passed。（`test_load_skill_markdown_reads_real_skill_file` は既存 `skills/crowdworks-proposal-writer/SKILL.md` に依存。存在しない場合は `projects/crowdworks_auto_apply/` 相対パスを見直す。）

- [ ] **Step 6: Commit**

```bash
git add projects/crowdworks_auto_apply/src/proposal_gen.py \
        projects/crowdworks_auto_apply/tests/test_proposal_gen.py \
        projects/crowdworks_auto_apply/tests/fixtures/sample_skill.md
git commit -m "feat(cw): add Sonnet 4.6 proposal generator with SKILL.md system injection"
```

---

### Task 9: Sheets クライアント（4 タブ構成）`src/sheets_client.py`

**Context:** v0.1 の 5 タブ構成（`draft_proposals` + `sent_log` 分離）を 4 タブに再編（PRD v0.2 §7.3）。Gmail 関連列（`gmail_draft_id`）を削除、`status` / `applied_at` / `owner_memo` に統一。

**Files:**
- Create: `projects/crowdworks_auto_apply/src/sheets_client.py`
- Test: `projects/crowdworks_auto_apply/tests/test_sheets_client.py`

**4 タブ列スキーマ（feasibility v0.2 §6 / PRD v0.2 F-41）:**

| タブ | 列（順序が append 引数順序と一致） |
|---|---|
| `master_jobs_raw` | `job_id | title | summary | url | posted_at | category | fetched_at` |
| `daily_candidates` | `date | job_id | score | title | url | category | tone_hint | reason | proposal_text | status | applied_at | owner_memo` |
| `execution_log` | `timestamp | phase | event | job_id | message` |
| `scoring_config` | `key | value`（Phase 1.5 予約、Phase 1 は空タブ） |

- [ ] **Step 1: RED**

`tests/test_sheets_client.py`:
```python
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.sheets_client import SheetsClient
from src.models import Job, Scored


def _ws(rows):
    """gspread Worksheet ダブル."""
    ws = MagicMock()
    ws.col_values.return_value = rows  # get_known_job_ids 用（1列目取得）
    ws.append_row = MagicMock()
    return ws


def _mock_gs(ws_by_name):
    gs = MagicMock()  # gspread.Client
    sh = MagicMock()  # Spreadsheet
    sh.worksheet.side_effect = lambda name: ws_by_name[name]
    gs.open_by_key.return_value = sh
    return gs


def test_from_file_opens_spreadsheet(mocker, tmp_path):
    fake_sa = tmp_path / "sa.json"
    fake_sa.write_text("{}")
    ws_by_name = {
        "master_jobs_raw": _ws(["job_id", "1", "2"]),
        "daily_candidates": _ws([]),
        "execution_log": _ws([]),
        "scoring_config": _ws([]),
    }
    mocker.patch("src.sheets_client.gspread.service_account", return_value=_mock_gs(ws_by_name))

    client = SheetsClient.from_file(str(fake_sa), spreadsheet_id="abc")
    assert client is not None


def test_get_known_job_ids_returns_set(mocker, tmp_path):
    fake_sa = tmp_path / "sa.json"; fake_sa.write_text("{}")
    ws_by_name = {
        "master_jobs_raw": _ws(["job_id", "100", "200", "300"]),
        "daily_candidates": _ws([]),
        "execution_log": _ws([]),
        "scoring_config": _ws([]),
    }
    mocker.patch("src.sheets_client.gspread.service_account", return_value=_mock_gs(ws_by_name))

    client = SheetsClient.from_file(str(fake_sa), spreadsheet_id="abc")
    ids = client.get_known_job_ids()
    assert ids == {"100", "200", "300"}


def test_append_master_job_writes_correct_order(mocker, tmp_path):
    fake_sa = tmp_path / "sa.json"; fake_sa.write_text("{}")
    master = _ws(["job_id"])
    ws_by_name = {
        "master_jobs_raw": master,
        "daily_candidates": _ws([]),
        "execution_log": _ws([]),
        "scoring_config": _ws([]),
    }
    mocker.patch("src.sheets_client.gspread.service_account", return_value=_mock_gs(ws_by_name))

    client = SheetsClient.from_file(str(fake_sa), spreadsheet_id="abc")
    job = Job(
        job_id="111", title="T", url="https://u",
        description="this is summary body (will be trimmed to 500 chars)",
        budget_text=None, category="システム開発",
        posted_at=None,
        scanned_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
    )
    client.append_master_job(job)

    args, kwargs = master.append_row.call_args
    row = args[0]
    # 列順: job_id | title | summary | url | posted_at | category | fetched_at
    assert row[0] == "111"
    assert row[1] == "T"
    assert row[3] == "https://u"
    assert row[5] == "システム開発"
    assert row[6].startswith("2026-04-24")


def test_append_daily_candidate_writes_12_cols(mocker, tmp_path):
    fake_sa = tmp_path / "sa.json"; fake_sa.write_text("{}")
    cand = _ws([])
    ws_by_name = {
        "master_jobs_raw": _ws([]),
        "daily_candidates": cand,
        "execution_log": _ws([]),
        "scoring_config": _ws([]),
    }
    mocker.patch("src.sheets_client.gspread.service_account", return_value=_mock_gs(ws_by_name))

    client = SheetsClient.from_file(str(fake_sa), spreadsheet_id="abc")
    job = Job(
        job_id="111", title="T", url="u", description="d",
        scanned_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
        category="システム開発",
    )
    scored = Scored(
        job=job, total_score=80, lucrative_score=25, fit_score=30,
        tone_hint="提案型", reason="fit", category_detected="GAS",
    )
    client.append_daily_candidate(scored, proposal_text="応募文ABC")

    args, _ = cand.append_row.call_args
    row = args[0]
    assert len(row) == 12
    # 列順: date | job_id | score | title | url | category | tone_hint | reason | proposal_text | status | applied_at | owner_memo
    assert row[1] == "111"
    assert row[2] == 80
    assert row[6] == "提案型"
    assert row[8] == "応募文ABC"
    assert row[9] == "PENDING"
    assert row[10] == ""  # applied_at 空
    assert row[11] == ""  # owner_memo 空


def test_append_execution_log(mocker, tmp_path):
    fake_sa = tmp_path / "sa.json"; fake_sa.write_text("{}")
    log = _ws([])
    ws_by_name = {
        "master_jobs_raw": _ws([]),
        "daily_candidates": _ws([]),
        "execution_log": log,
        "scoring_config": _ws([]),
    }
    mocker.patch("src.sheets_client.gspread.service_account", return_value=_mock_gs(ws_by_name))

    client = SheetsClient.from_file(str(fake_sa), spreadsheet_id="abc")
    client.append_execution_log(phase="fetch", event="info", job_id="", message="started")
    args, _ = log.append_row.call_args
    row = args[0]
    assert len(row) == 5
    assert row[1] == "fetch"
    assert row[2] == "info"
    assert row[4] == "started"


def test_from_json_uses_service_account_from_dict(mocker):
    # audit M-5 対応: from_json 経路は service_account_from_dict のみ叩く
    sa_json = json.dumps({"type": "service_account"})
    ws_by_name = {
        "master_jobs_raw": _ws([]),
        "daily_candidates": _ws([]),
        "execution_log": _ws([]),
        "scoring_config": _ws([]),
    }
    patched = mocker.patch(
        "src.sheets_client.gspread.service_account_from_dict",
        return_value=_mock_gs(ws_by_name),
    )
    patched_file = mocker.patch("src.sheets_client.gspread.service_account")

    SheetsClient.from_json(sa_json, spreadsheet_id="abc")

    patched.assert_called_once()
    patched_file.assert_not_called()  # from_file 側は呼ばれない
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_sheets_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.sheets_client'`。

- [ ] **Step 3: GREEN**

`src/sheets_client.py`:
```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Set

import gspread

from src.models import Job, Scored


TAB_MASTER = "master_jobs_raw"
TAB_CANDIDATES = "daily_candidates"
TAB_LOG = "execution_log"
TAB_SCORING = "scoring_config"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _truncate(text: str, limit: int = 500) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SheetsClient:
    """gspread ラッパ (4 タブ構成)."""

    def __init__(self, gs_client: gspread.Client, spreadsheet_id: str) -> None:
        self._gs = gs_client
        self._sh = gs_client.open_by_key(spreadsheet_id)
        self._master = self._sh.worksheet(TAB_MASTER)
        self._candidates = self._sh.worksheet(TAB_CANDIDATES)
        self._log = self._sh.worksheet(TAB_LOG)
        self._scoring = self._sh.worksheet(TAB_SCORING)

    @classmethod
    def from_file(cls, service_account_file: str, spreadsheet_id: str) -> "SheetsClient":
        gs = gspread.service_account(filename=service_account_file)
        return cls(gs, spreadsheet_id)

    @classmethod
    def from_json(cls, service_account_json: str, spreadsheet_id: str) -> "SheetsClient":
        info = json.loads(service_account_json)
        gs = gspread.service_account_from_dict(info)
        return cls(gs, spreadsheet_id)

    def get_known_job_ids(self) -> Set[str]:
        col = self._master.col_values(1)
        # ヘッダ除去
        return {v for v in col[1:] if v}

    def append_master_job(self, job: Job) -> None:
        row = [
            job.job_id,
            job.title,
            _truncate(job.description or "", 500),
            job.url,
            _iso(job.posted_at) if job.posted_at else "",
            job.category or "",
            _iso(job.scanned_at),
        ]
        self._master.append_row(row, value_input_option="RAW")

    def append_daily_candidate(self, scored: Scored, proposal_text: str) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        row = [
            today,
            scored.job.job_id,
            scored.total_score,
            scored.job.title,
            scored.job.url,
            scored.job.category or "",
            scored.tone_hint,
            scored.reason,
            proposal_text,
            "PENDING",
            "",
            "",
        ]
        self._candidates.append_row(row, value_input_option="RAW")

    def append_execution_log(
        self, phase: str, event: str, job_id: str, message: str,
    ) -> None:
        row = [
            _iso(datetime.now(timezone.utc)),
            phase,
            event,
            job_id,
            message,
        ]
        self._log.append_row(row, value_input_option="RAW")
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_sheets_client.py -v
```

Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/sheets_client.py \
        projects/crowdworks_auto_apply/tests/test_sheets_client.py
git commit -m "feat(cw): rework sheets_client to 4-tab schema (drop gmail draft columns)"
```

---

### Task 10: main オーケストレーション（`src/main.py`）

**Context:** v0.1 の Gmail 下書き作成ステップ（旧 Task 10）を完全削除し、Sheets 直接書き込みのみで完結させる。

**Files:**
- Create: `projects/crowdworks_auto_apply/src/main.py`
- Test: `projects/crowdworks_auto_apply/tests/test_main.py`

- [ ] **Step 1: RED**

`tests/test_main.py`:
```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.main import run_pipeline
from src.models import Job, Scored


def _job(jid: str) -> Job:
    return Job(
        job_id=jid, title=f"T{jid}", url=f"https://u/{jid}",
        description="d" * 200, category="システム開発",
        scanned_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
    )


def test_run_pipeline_happy_path(mocker, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "./sa.json")

    fetcher = MagicMock()
    fetcher.assert_robots_allows = MagicMock()
    fetcher.fetch_all.return_value = [_job("1"), _job("2")]

    sheets = MagicMock()
    sheets.get_known_job_ids.return_value = set()

    def _score(job, **kwargs):
        return Scored(
            job=job, total_score=80, lucrative_score=20, fit_score=30,
            tone_hint="提案型", reason="fit", category_detected="GAS",
        )

    mocker.patch("src.main.Fetcher", return_value=fetcher)
    mocker.patch("src.main.RateLimitedClient")
    mocker.patch("src.main.SheetsClient.from_file", return_value=sheets)
    mocker.patch("src.main.score_job", side_effect=_score)
    mocker.patch("src.main.generate_proposal", return_value="応募文X")
    mocker.patch("src.main.load_skill_markdown", return_value="skill body")
    mocker.patch("src.main.Anthropic")

    run_pipeline()

    # master_jobs_raw に 2 件、daily_candidates に 2 件、execution_log に ≥2 件
    assert sheets.append_master_job.call_count == 2
    assert sheets.append_daily_candidate.call_count == 2
    assert sheets.append_execution_log.called


def test_run_pipeline_records_fetch_failure(mocker, monkeypatch):
    from src.http_client import BlockedError
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("SPREADSHEET_ID", "abc")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "./sa.json")

    fetcher = MagicMock()
    fetcher.assert_robots_allows.side_effect = BlockedError("blocked 403")

    sheets = MagicMock()
    mocker.patch("src.main.Fetcher", return_value=fetcher)
    mocker.patch("src.main.RateLimitedClient")
    mocker.patch("src.main.SheetsClient.from_file", return_value=sheets)

    # BlockedError でも run_pipeline 本体は例外を吐かず execution_log に記録
    run_pipeline()
    # fatal / blocked イベントがログされる
    calls = [c.kwargs for c in sheets.append_execution_log.call_args_list]
    events = [c.get("event") for c in calls]
    assert "blocked" in events or "fatal" in events
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.main'`。

- [ ] **Step 3: GREEN**

`src/main.py`:
```python
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

import requests
from anthropic import Anthropic

from src.config import Config
from src.fetcher import Fetcher, RobotsDisallowedError
from src.filter import select_candidates
from src.http_client import RateLimitedClient, BlockedError
from src.idempotency import filter_new_jobs
from src.models import Job, Scored
from src.proposal_gen import generate_proposal, load_skill_markdown
from src.scorer import score_job
from src.sheets_client import SheetsClient


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills" / "crowdworks-proposal-writer" / "SKILL.md"
)


def _build_sheets_client(cfg: Config) -> SheetsClient:
    if cfg.google_service_account_json:
        return SheetsClient.from_json(cfg.google_service_account_json, cfg.spreadsheet_id)
    return SheetsClient.from_file(cfg.google_service_account_file, cfg.spreadsheet_id)


def run_pipeline() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("cw.main")

    cfg = Config.from_env()
    sheets = _build_sheets_client(cfg)

    session = requests.Session()
    http = RateLimitedClient(
        session=session,
        user_agent=cfg.user_agent,
        timeout=cfg.request_timeout,
        interval_sec=cfg.request_interval_sec,
        max_attempts=cfg.retry_max_attempts,
        backoff_base=cfg.retry_backoff_base,
    )
    fetcher = Fetcher(cfg, http)

    # --- 1. robots.txt guard ---
    try:
        fetcher.assert_robots_allows("/public/jobs")
        sheets.append_execution_log(phase="fetch", event="info", job_id="", message="robots.txt ok")
    except RobotsDisallowedError as exc:
        sheets.append_execution_log(phase="fetch", event="fatal", job_id="", message=f"robots_disallow: {exc}")
        log.error("robots.txt disallows /public/jobs: %s", exc)
        return
    except BlockedError as exc:
        sheets.append_execution_log(phase="fetch", event="blocked", job_id="", message=str(exc))
        log.error("blocked while fetching robots.txt: %s", exc)
        return
    except Exception as exc:  # noqa: BLE001
        sheets.append_execution_log(phase="fetch", event="fatal", job_id="", message=f"robots_check_error: {exc}")
        log.exception("robots check unexpected error")
        return

    # --- 2. fetch ---
    try:
        all_jobs: List[Job] = fetcher.fetch_all()
    except BlockedError as exc:
        sheets.append_execution_log(phase="fetch", event="blocked", job_id="", message=str(exc))
        log.error("blocked while fetching: %s", exc)
        return
    except Exception as exc:  # noqa: BLE001
        sheets.append_execution_log(phase="fetch", event="fatal", job_id="", message=f"fetch_error: {exc}")
        log.exception("fetch_all failed")
        return
    sheets.append_execution_log(phase="fetch", event="info", job_id="", message=f"fetched={len(all_jobs)}")

    # --- 3. idempotency ---
    try:
        new_jobs = filter_new_jobs(all_jobs, sheets)
    except Exception as exc:  # noqa: BLE001
        sheets.append_execution_log(phase="fetch", event="fatal", job_id="", message=f"idempotency_error: {exc}")
        log.exception("idempotency failed")
        return
    sheets.append_execution_log(phase="fetch", event="info", job_id="", message=f"new_jobs={len(new_jobs)}")

    # --- 4. persist raw master ---
    for job in new_jobs:
        try:
            sheets.append_master_job(job)
        except Exception as exc:  # noqa: BLE001
            sheets.append_execution_log(phase="persist", event="warning", job_id=job.job_id, message=f"master_append_error: {exc}")

    # --- 5. score ---
    anthropic_client = Anthropic(api_key=cfg.anthropic_api_key)
    scored: List[Scored] = []
    for job in new_jobs:
        try:
            s = score_job(job, client=anthropic_client, model=cfg.haiku_model)
            scored.append(s)
        except Exception as exc:  # noqa: BLE001
            sheets.append_execution_log(phase="score", event="warning", job_id=job.job_id, message=f"score_error: {exc}")
    sheets.append_execution_log(phase="score", event="info", job_id="", message=f"scored={len(scored)}")

    # --- 6. filter ---
    candidates = select_candidates(
        scored, threshold=cfg.score_threshold, daily_limit=cfg.daily_apply_limit,
    )
    sheets.append_execution_log(phase="score", event="info", job_id="", message=f"candidates={len(candidates)}")

    # --- 7. proposal generation + persist ---
    try:
        skill_md = load_skill_markdown(SKILL_PATH)
    except FileNotFoundError as exc:
        sheets.append_execution_log(phase="generate", event="fatal", job_id="", message=f"skill_not_found: {exc}")
        log.error("SKILL.md not found at %s", SKILL_PATH)
        return

    for s in candidates:
        try:
            proposal = generate_proposal(
                s, skill_markdown=skill_md, client=anthropic_client,
                model=cfg.sonnet_model, max_tokens=2048,
            )
        except Exception as exc:  # noqa: BLE001
            sheets.append_execution_log(phase="generate", event="warning", job_id=s.job.job_id, message=f"gen_error: {exc}")
            continue
        try:
            sheets.append_daily_candidate(s, proposal_text=proposal)
            sheets.append_execution_log(phase="persist", event="info", job_id=s.job.job_id, message=f"score={s.total_score}")
        except Exception as exc:  # noqa: BLE001
            sheets.append_execution_log(phase="persist", event="warning", job_id=s.job.job_id, message=f"candidate_append_error: {exc}")

    sheets.append_execution_log(phase="persist", event="info", job_id="", message="run complete")


if __name__ == "__main__":
    run_pipeline()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_main.py -v
```

Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add projects/crowdworks_auto_apply/src/main.py \
        projects/crowdworks_auto_apply/tests/test_main.py
git commit -m "feat(cw): wire fetcher->scorer->filter->proposalgen->sheets, drop gmail step"
```

---

### Task 11: GitHub Actions ワークフロー（`.github/workflows/daily.yml`）

**Context:** v0.1 の `cron: "0 0 * * *"` を `cron: "22 0 * * *"`（09:22 JST、非ピッタリ時刻）に変更（audit M-4 対応）。Gmail 関連 Secret を削除、Anthropic API キーと Sheets のみに集約。

**Files:**
- Create: `projects/crowdworks_auto_apply/.github/workflows/daily.yml`

- [ ] **Step 1: ワークフロー作成**

`projects/crowdworks_auto_apply/.github/workflows/daily.yml`:
```yaml
name: crowdworks-daily

on:
  schedule:
    # UTC 00:22 = JST 09:22 daily (avoid :00 congestion on GitHub Actions)
    - cron: "22 0 * * *"
  workflow_dispatch: {}

concurrency:
  group: crowdworks-daily
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    defaults:
      run:
        working-directory: projects/crowdworks_auto_apply
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: projects/crowdworks_auto_apply/requirements.txt

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ANTHROPIC_HAIKU_MODEL: ${{ secrets.ANTHROPIC_HAIKU_MODEL }}
          ANTHROPIC_SONNET_MODEL: ${{ secrets.ANTHROPIC_SONNET_MODEL }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
          CROWDWORKS_LIST_URL: https://crowdworks.jp/public/jobs?order=new
          CROWDWORKS_DETAIL_URL_TEMPLATE: https://crowdworks.jp/public/jobs/{job_id}
          CROWDWORKS_ROBOTS_URL: https://crowdworks.jp/robots.txt
          USER_AGENT: "TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)"
          REQUEST_TIMEOUT: "30"
          REQUEST_INTERVAL_SEC: "1.0"
          MAX_DETAIL_FETCH: "30"
          RETRY_MAX_ATTEMPTS: "2"
          RETRY_BACKOFF_BASE: "2.0"
          SELECTOR_JOB_ITEM: ${{ secrets.SELECTOR_JOB_ITEM }}
          SELECTOR_JOB_LINK: ${{ secrets.SELECTOR_JOB_LINK }}
          SELECTOR_JOB_TITLE: ${{ secrets.SELECTOR_JOB_TITLE }}
          SELECTOR_JOB_POSTED_AT: ${{ secrets.SELECTOR_JOB_POSTED_AT }}
          SELECTOR_JOB_CATEGORY: ${{ secrets.SELECTOR_JOB_CATEGORY }}
          SELECTOR_DETAIL_BODY: ${{ secrets.SELECTOR_DETAIL_BODY }}
          SELECTOR_DETAIL_BUDGET: ${{ secrets.SELECTOR_DETAIL_BUDGET }}
          DAILY_APPLY_LIMIT: "10"
          SCORE_THRESHOLD: "60"
        run: python -m src.main
```

[Fact] GitHub Actions の scheduled workflow は `:00` ピッタリ時刻で混雑・遅延しやすい（audit M-4、feasibility v0.2 §1）。`22 0 * * *`（UTC）＝ JST 09:22 はピーク帯から 22 分ずらした安全側時刻。

[Inference] セレクタ群を Secret 経由で注入するのは、HTML 構造変化時にコード変更・再デプロイなしに .env 側だけで差替可能とするため（feasibility v0.2 §8 R1 緩和策）。Secret が空文字列の場合は `config.py` のデフォルト値が使われる。

- [ ] **Step 2: Commit**

```bash
git add projects/crowdworks_auto_apply/.github/workflows/daily.yml
git commit -m "ci(cw): daily cron at 09:22 JST with anthropic+sheets secrets only"
```

---

### Task 12: README + 実運用 smoke test（verification-before-completion 適用）

**Context:** 最終タスクでは `shared_knowledge/skills/verification-before-completion/SKILL.md` の原則に従い、「証拠なき完了宣言」を禁止する。README 整備と、ローカル手動実行 → Sheets 実データ書込 → 証拠スクリーンショットの手順を明記。

**Files:**
- Create: `projects/crowdworks_auto_apply/README.md`

- [ ] **Step 1: README 作成**

`projects/crowdworks_auto_apply/README.md`:
````markdown
# CrowdWorks 自動応募システム Phase 1（半自動 MVP）v0.2

CrowdWorks 公開 HTML（`/public/jobs?order=new`）をスクレイピングし、Claude Haiku 4.5 でスコアリング → Claude Sonnet 4.6 + 既存 `skills/crowdworks-proposal-writer/SKILL.md` 注入で応募文生成 → Google Sheets（4 タブ）に直接書き込む半自動パイプライン。Gmail API は使わない。送信はオーナーが CrowdWorks サイト上で手動実施し、Sheets 上で status を APPLIED に更新する。

## アーキテクチャ

```
[robots.txt check] -> [requests+BS4 scrape list] -> [requests+BS4 scrape detail]
  -> [filter known job_ids via master_jobs_raw] -> [Claude Haiku 4.5 score]
  -> [threshold 60 + regex exclude + daily_limit 10]
  -> [Claude Sonnet 4.6 + SKILL.md system injection]
  -> [Google Sheets daily_candidates append]
  -> [human opens Sheets, clicks URL, copy-paste proposal, submit on CrowdWorks, set status=APPLIED]
```

## セットアップ手順（初回のみ）

### 1. Google Cloud プロジェクト準備
1. GCP でプロジェクト作成、**Google Sheets API のみ有効化**（Gmail API は不要）
2. Service Account を作成し、鍵を JSON でダウンロード（ファイル名任意、`service_account.json` 推奨）
3. Google Workspace のドメイン委任は**不要**（v0.1 の要件は撤回済み）

### 2. スプレッドシート準備
1. 新規スプレッドシート作成、ID を控える（URL の `/d/<ID>/`）
2. 以下 **4 タブ**を作成し、1 行目に列ヘッダを設定:
   - `master_jobs_raw`: `job_id | title | summary | url | posted_at | category | fetched_at`
   - `daily_candidates`: `date | job_id | score | title | url | category | tone_hint | reason | proposal_text | status | applied_at | owner_memo`
   - `execution_log`: `timestamp | phase | event | job_id | message`
   - `scoring_config`: `key | value`（Phase 1 は空タブで可）
3. スプレッドシートを Service Account のメールアドレスに「編集者」で共有

### 3. API キー取得
- `ANTHROPIC_API_KEY`: https://console.anthropic.com/settings/keys
- Gemini / Google AI Studio のキーは**不要**（v0.1 から撤回）

### 4. ローカル動作確認（smoke test）
```bash
cd projects/crowdworks_auto_apply
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env を編集:
#   - ANTHROPIC_API_KEY を設定
#   - SPREADSHEET_ID を設定
#   - service_account.json を同ディレクトリに配置し GOOGLE_SERVICE_ACCOUNT_FILE を設定
#   - 実機で crowdworks.jp/public/jobs?order=new を開き、DevTools でセレクタを確認して SELECTOR_* を上書き

pytest -v          # 全テスト通過を確認
python -m src.main # 実 API を叩く手動実行
```

**証拠（verification-before-completion）**:
実行後、以下の**4 つの証拠**を `requirements/evidence/YYYYMMDD_smoke/` に保存して初めて「Phase 1 実装完了」と報告可能:

1. `pytest_all_green.png` — `pytest -v` の出力スクショ（全 pass）
2. `sheets_master.png` — `master_jobs_raw` に N 行追加された状態
3. `sheets_candidates.png` — `daily_candidates` に 1 行以上 `proposal_text` 付きで追加された状態
4. `sheets_log.png` — `execution_log` に `fetch info / score info / persist info` が記録された状態

### 5. GitHub Actions への設定
Secrets:
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_HAIKU_MODEL`（空でも可、デフォルト `claude-haiku-4-5-20251001`）
- `ANTHROPIC_SONNET_MODEL`（空でも可、デフォルト `claude-sonnet-4-6`）
- `GOOGLE_SERVICE_ACCOUNT_JSON`（`service_account.json` の中身を**1 行化**して貼付。改行エスケープ崩れ対策）
- `SPREADSHEET_ID`
- `SELECTOR_JOB_ITEM` / `SELECTOR_JOB_LINK` / `SELECTOR_JOB_TITLE` / `SELECTOR_JOB_POSTED_AT` / `SELECTOR_JOB_CATEGORY` / `SELECTOR_DETAIL_BODY` / `SELECTOR_DETAIL_BUDGET`（構造変化時に上書き用）

初回は Actions タブから `crowdworks-daily` を `workflow_dispatch` で手動実行し、成功を確認。以降は毎朝 JST 09:22 前後（最大 30 分遅延あり）に自動起動。

## 運用ルール（厳守）

- **送信は必ずオーナーが CrowdWorks サイト上で実施**。本システムは Sheets 書き込みまでしか行わない。
- **日次上限 10 件**。Secrets で `DAILY_APPLY_LIMIT` を変えれば増減可能だが、Exit Criteria 達成まで 10 件固定を推奨。
- **取得頻度は 1 日 1 回が基本**。`workflow_dispatch` の追加実行は必要時のみ、同日 2 回以内に抑える（feasibility v0.2 §3.4）。
- **SKILL.md は改変しない**。応募文ルール変更は `skills/crowdworks-proposal-writer/SKILL.md` の書換で反映される（system prompt への自動同期）。
- **HTML 構造変化検知時は即対応**。`execution_log` に `selector_miss` / `fatal` が記録されたら、Woz が実機 HTML を取得 → セレクタを更新 → `SELECTOR_*` Secret を書換。

## トラブルシュート

| 症状 | 切り分け | 対処 |
|---|---|---|
| `execution_log` に `blocked` が記録される | 403 / 429 / 503 のいずれか確認 | Cloudflare / Bot 検知発動。回避せず**即停止**し、オーナーに手動 URL 入力フォールバックを提案 |
| `execution_log` に `robots_disallow` が記録される | `crowdworks.jp/robots.txt` を実機で開き `/public/` が Disallow 化されていないか確認 | CrowdWorks 側の規約改定の可能性。Phase 1 停止 → Jobs 報告 → 設計再審査 |
| `execution_log` に `selector_miss` が記録される | `curl -H "User-Agent: TEGG-CrowdWorks-JobFetcher/0.2 ..." https://crowdworks.jp/public/jobs?order=new` で生 HTML 取得、DevTools でセレクタ再確認 | `SELECTOR_*` Secret を書換、手動 `workflow_dispatch` で再実行 |
| `daily_candidates` に重複行 | `master_jobs_raw` の `job_id` 列に同 ID があるか | `idempotency.filter_new_jobs` が呼ばれていない可能性。`execution_log` の `new_jobs=N` を確認 |
| Haiku が常に `total_score=0` | `tests/test_scorer.py` で JSON パースが通るか確認 | モデル応答に前置きが混入している。`SYSTEM_PROMPT` 末尾「JSON のみ」指示を強化して再デプロイ |
| `Service Account JSON が無効` エラー | GitHub Secret の改行崩れ | `GOOGLE_SERVICE_ACCOUNT_JSON` を 1 行化し直して再登録。**誤って Git commit した場合は即 Service Account を削除・再発行** |

## Exit Criteria（Phase 2 移行判定、PRD v0.2 §8 と同義）

- オーナー応募採用率 70% 以上（直近連続 30 件）
- 応募→返信率 15% 以上（連続 2 ヶ月）
- CrowdWorks 規約違反警告・制限・BAN が連続 90 日ゼロ
- スコアリング誤判定月 5 件未満
- オーナー主観満足度 4/5 以上（連続 3 ヶ月）

達成後、Rubinstein 監査を経て Phase 2 PRD を別途起案する。Phase 2 は完全自動送信の検討を含むが、CrowdWorks 規約の解釈次第では永続的に Phase 1 運用を継続する判断もあり得る。

## バージョン履歴
- v0.2 (2026-04-24): 全面書き直し。RSS/Gemini/Gmail 撤回、HTML スクレイピング + Anthropic 単一プロバイダ + Sheets 直書きへ刷新
- v0.1 (2026-04-21): 初版（RSS/Gemini/Gmail 前提、本版で破棄）
````

- [ ] **Step 2: 実運用 smoke test 実施 + 証拠収集（verification-before-completion 遵守）**

verification-before-completion SKILL に従い、以下の手順を**必ず実機で実行**して証拠画像を保存するまで「完了」と宣言しない:

1. オーナーの作業: Anthropic API キー取得 / Service Account 作成（Sheets API のみ）/ Sheets 4 タブ初期化
2. Woz が手動 smoke test 実行:
   - 実機で `crowdworks.jp/public/jobs?order=new` を開き、DevTools でセレクタを取得、`.env` の `SELECTOR_*` を上書き
   - `python -m src.main` を実行（1 回）
   - Sheets の `master_jobs_raw` / `daily_candidates` / `execution_log` の状態をスクリーンショット
3. 証拠を `projects/crowdworks_auto_apply/requirements/evidence/YYYYMMDD_smoke/` に保存:
   - `pytest_all_green.png`
   - `sheets_master.png`
   - `sheets_candidates.png`
   - `sheets_log.png`
   - `robots_txt_YYYYMMDD.png`（feasibility v0.2 §2.4 の月次ルーチン初回分）
4. オーナーに報告: `daily_candidates` に書かれた応募文の品質を目視確認してもらい、1 件を CrowdWorks サイトで実際にコピペ送信 → `status=APPLIED` に更新する運用を 1 サイクル完走
5. GitHub Actions `workflow_dispatch` で手動起動し、Actions ログの成功を確認 → スクショ `gha_success.png`

- [ ] **Step 3: Commit**

```bash
git add projects/crowdworks_auto_apply/README.md
git commit -m "docs(cw): add v0.2 operations README with evidence-based verification"
```

- [ ] **Step 4: Verification 完了宣言の条件**

以下**全て**を満たした時点で初めて Jobs に「Phase 1 実装完了」を報告:

- [ ] `pytest -v` の全テスト（Task 2〜10 合計）が PASS
- [ ] ローカル `python -m src.main` の 1 回実行成功（5 つの証拠画像揃っている）
- [ ] GitHub Actions `workflow_dispatch` の 1 回実行成功（`gha_success.png` 揃っている）
- [ ] オーナーが `daily_candidates` の 1 件で実応募 → `status=APPLIED` サイクルを完走
- [ ] Rubinstein に再監査を依頼し GO 判定取得

証拠不足のまま完了報告した場合は第2条（ハルシネーション禁止）違反として Jobs が差し戻す。

---

## 3. Self-Review（writing-plans スキル準拠、Woz 自身で実施した結果）

### 3.1 Spec coverage（PRD v0.2 / feasibility v0.2 / audit 指摘の対応表）

| 要件 / 指摘 | 対応タスク |
|---|---|
| PRD F-01 GitHub Actions cron 非ピッタリ | Task 11（`22 0 * * *`）|
| PRD F-02 `/public/jobs` 対象 | Task 4（`CROWDWORKS_LIST_URL` デフォルト）|
| PRD F-04 HTML スクレイピング + BS4 | Task 4 Fetcher |
| PRD F-05 Rate Limit 1 秒/req | Task 4 RateLimitedClient |
| PRD F-06 robots.txt 遵守 + User-Agent | Task 4 assert_robots_allows + http_client 初期化 |
| PRD F-07 1 回あたり 100 件上限 | Task 3 `MAX_DETAIL_FETCH=30`（詳細取得のみ制限、一覧は全件取得）|
| PRD F-10 正規化 Job | Task 2 |
| PRD F-20/21 Haiku 4.5 スコアリング | Task 6 |
| PRD F-22 モデル ID 環境変数化 | Task 3 Config, Task 6 引数, Task 11 Secrets |
| PRD F-23 60 点閾値 | Task 7 |
| PRD F-30 Sonnet 4.6 応募文生成 | Task 8 |
| PRD F-31 モデル ID 環境変数化 | Task 3 Config, Task 8 引数 |
| PRD F-32 SKILL.md 注入 | Task 8 load_skill_markdown + system 引数 |
| PRD F-33 絶対ルール 10 項目保全 | Task 8（ファイル書換禁止、読込のみ）|
| PRD F-40/41 Sheets 4 タブ / 12 列 | Task 9 |
| PRD F-42 status=PENDING 初期値 | Task 9 append_daily_candidate |
| PRD F-43 draft_proposals / sent_log 廃止 | Task 9（4 タブ構成）|
| PRD F-44 冪等性 | Task 5 idempotency |
| PRD F-74 10 件上限 | Task 3/7 `DAILY_APPLY_LIMIT=10` |
| PRD F-80 GitHub Actions 確定 | Task 11 |
| PRD F-81 非ピッタリ cron | Task 11 `22 0 * * *` |
| PRD F-90 execution_log | Task 9/10 |
| PRD NFR-01〜05 規約遵守 | Task 4 robots + UA、Task 10 blocked 即停止 |
| PRD NFR-20/21 `.env` / `.gitignore` | Task 1 |
| PRD NFR-22 Sheets API のみ | Task 1 `.env.example`、Task 12 README |
| PRD NFR-41 HTTP リトライ 3 回（指数バックオフ） | Task 4 http_client `RETRY_MAX_ATTEMPTS=2`（5xx のみ）+ 403/429/503 は即停止 [Inference: PRD の「3 回」は 5xx の再試行文脈と解釈し、最大 2 attempts = 初回+リトライ 2 回 で実効 3 試行] |
| feasibility C1 robots 月次監査 | Task 12 README §2.4 相当の運用ルール明記 |
| feasibility C2 HTML 構造フォールバック | Task 4 selector_miss warning + Task 11 Secrets 差替 |
| feasibility C3 1 日 1-2 回 | Task 11 cron 1 日 1 回 + workflow_dispatch 運用ルール |
| feasibility C4 User-Agent 明示 | Task 3 Config デフォルト |
| feasibility C5 Cloudflare 即停止 | Task 4 BlockedError |
| feasibility C6 Phase 2 再審査 | Task 12 README Exit Criteria |
| audit C-1 RSS URL 不一致 | **自動解消**（Task 4 で HTML 取得に完全移行）|
| audit C-2 Claude モデル ID 最新版 | Task 3 環境変数化、Task 8 引数渡し |
| audit C-3 google-generativeai 廃止 | **自動解消**（Task 6 Anthropic SDK へ置換）|
| audit M-1 Gemini 単価誤り | **自動解消**（Gemini 撤回）|
| audit M-2 Sheets 列スキーマ不整合 | Task 9（PRD v0.2 と一致する 4 タブ 12 列）|
| audit M-3 Gmail ドメイン委任不可 | **自動解消**（Gmail 撤回）|
| audit M-4 cron `:00` 遅延 | Task 11 `22 0 * * *` |
| audit M-5 test_sheets_client モック重複 | Task 9 テストで `from_file` と `from_json` を分離、それぞれ単独パッチ |
| audit M-6 filter 部分一致 | Task 7 正規表現 `\b` + タイトル vs 本文分離 |
| audit M-7 `.env.example` 秘密鍵扱い | Task 1 `.env.example` コメント + Task 12 README トラブルシュート |
| audit m-1〜m-6 PRD 文言不整合 | Federighi PRD v0.2 で対応済み、本計画は整合を反映 |

**ギャップ検知:**
- PRD NFR-24「クライアント企業機微情報 180 日自動削除」は Phase 1 実装スコープ外（Phase 1.5 予約）として Task 12 README に明示済み。Phase 1 本計画では実装タスクを切らない。
- `scoring_config` タブの Phase 1 実装は空タブ作成のみ（Task 12 README §2）、動的読込は Phase 1.5。
- `posted_at` の正確なパースは着手時点の実機 HTML 次第（Task 4 Step 8 Inference 記述）。本計画では `None` 固定で運用開始し、HTML 構造確定後に改修。

### 3.2 Placeholder scan（writing-plans 禁止事項の自己検査）

- `"TBD"` / `"TODO"` / `"implement later"` / `"fill in details"` / `"Similar to Task N"` / `"add appropriate error handling"` の検索結果: **本計画内に該当なし**
- セレクタのデフォルト値は `[Inference]` として明示し「着手時に実機確認して上書き」と記述（プレースホルダではない）
- `posted_at=None` 固定の妥協は [Inference] 付きで根拠を明示
- エラーハンドリングは Task 10 で `BlockedError` / `RobotsDisallowedError` / `FileNotFoundError` / `Exception` のそれぞれに対応する execution_log の `phase` / `event` / `message` を具体記述

### 3.3 Type consistency（型・メソッド名一貫性）

- `Job` フィールド: `job_id / title / url / description / budget_text / category / posted_at / scanned_at` → Task 2 定義、Task 4/5/6/8/9/10 参照で一貫
- `Scored` フィールド: `job / total_score / lucrative_score / fit_score / tone_hint / reason / category_detected` → Task 2 定義、Task 6/7/8/9/10 で一貫使用
- `Config` フィールド: Task 3 で定義した全フィールドを Task 4/10 が参照（名前一致確認済）
- `RateLimitedClient.get(url)` / `BlockedError` → Task 4 定義、Task 10 利用
- `Fetcher.assert_robots_allows(path) / fetch_list() / fetch_detail(url) / fetch_all()` → Task 4 定義、Task 10 利用
- `SheetsClient.from_file / from_json / get_known_job_ids / append_master_job / append_daily_candidate / append_execution_log` → Task 9 定義、Task 10 利用で一貫
- `score_job(job, client, model) -> Scored` → Task 6 定義、Task 10 呼出で引数キーワード一致
- `generate_proposal(scored, skill_markdown, client, model, max_tokens) -> str` → Task 8 定義、Task 10 呼出で引数キーワード一致
- `load_skill_markdown(path) -> str` → Task 8 定義、Task 10 で `SKILL_PATH` 固定値に対して呼出
- `select_candidates(scored, threshold, daily_limit)` → Task 7 定義、Task 10 呼出で一致
- `filter_new_jobs(jobs, sheets)` → Task 5 定義、Task 10 呼出で一致

### 3.4 修正事項

Self-Review 中に検出・修正したもの:
- Task 9 の `append_daily_candidate` 列順を 12 要素に確定し、PRD v0.2 F-41 と一致させた（v0.1 の 12 列 `gmail_draft_id` を削除し、`tone_hint / reason / proposal_text / status / applied_at / owner_memo` を含む新 12 列構成に置換）
- Task 10 の `run_pipeline` が `BlockedError` / `RobotsDisallowedError` のいずれでも `sys.exit` せず `execution_log` に記録して正常終了する設計とし、GitHub Actions 実行が赤ランプで止まるのを回避（翌日再実行のため）
- Task 4 の `_parse_robots` を独自実装にした理由: Python 標準 `urllib.robotparser` は User-agent: `*` のグループを正確に扱うが、Allow/Disallow の語彙検証が目的のため依存追加を避け最小実装で足りると判断
- Task 6 の `score_job` で JSON パース失敗時に `total_score=0` を返す設計は、Task 7 で閾値 60 未満として自然に除外されるため、別途エラー伝搬を不要にした

### 3.5 writing-plans 準拠チェックリスト

- [x] 計画ヘッダに `Goal` / `Architecture` / `Tech Stack` を明記
- [x] `For agentic workers:` の REQUIRED SUB-SKILL 注記を保持
- [x] `## File Structure` テーブルを各ファイルの責務込みで記載
- [x] 各タスクを 2-5 分粒度の `- [ ]` チェックボックスに分解
- [x] RED → GREEN → REFACTOR（本計画では REFACTOR を各 GREEN 内最小化、別タスクでの大規模再設計は実施しない）を各タスクで明示
- [x] 完全コード（関数シグネチャのみの放置なし）を全ステップに記述
- [x] 最終タスク（Task 12）に verification-before-completion を適用、証拠なき完了宣言を禁止
- [x] `[Fact]` / `[Inference]` / `[Unknown]` のデータ系譜ラベルを根拠記述に付与（第1条遵守）

---

**最終更新**: 2026-04-24 / **改訂者**: Woz (CTO) / **バージョン**: v0.2 / **前版**: v0.1 (2026-04-21)
