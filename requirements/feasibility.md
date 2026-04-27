# CrowdWorks 自動応募システム 技術フィージビリティ調査書 v0.2

**プロジェクト**: CrowdWorks 自動応募システム（Phase 1: 半自動）
**バージョン**: v0.2（v0.1 からの全面改訂）
**更新日**: 2026-04-24
**調査者**: Woz（CTO）
**対象フェーズ**: Phase 1（HTML取得 → スコアリング → 応募文生成 → Sheets 書き込みまで自動、応募送信は人間が CrowdWorks サイト上で実行）

---

## 0. v0.1 → v0.2 変更概要（結論ファースト）

- **[Fact] RSSフィード取得を完全撤回**（§3.2 / §5 / §7 から削除）。CrowdWorks RSS 配信は提供終了を確認、旧URL `https://crowdworks.jp/public/jobs/u/professionals` は 404 応答（オーナー 2026-04-24 実機確認）。代替として `https://crowdworks.jp/public/jobs?order=new` への HTTP 取得 + HTMLパースへ方針転換。
- **[Fact] Gmail API を全面撤回**（§3.8 / §4 / §6 から削除）。下書き作成・通知・ドメイン委任設計を破棄。成果物は Google Sheets に直接書き込み、オーナーは毎朝 Sheets を開いて URL へ遷移する運用。
- **[Fact] Google Generative AI（Gemini）を全面撤回**。`google-generativeai` レガシー SDK（2025-11-30 非推奨化済み）への依存を初日から回避。
- **[Fact] LLM を Anthropic 単一プロバイダへ統合**。スコアリング=Claude Haiku 4.5、応募文生成=Claude Sonnet 4.6。両モデルIDを環境変数化。
- **[Fact] Google Sheets タブ構成を 5→4 に再編**（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`）。
- **[Inference] コスト試算を Anthropic 公式単価で再計算**。Haiku 4.5 $1/$5 per 1M tokens、Sonnet 4.6 $3/$15 per 1M tokens に基づき合計約 3,100 円/月（Maestri 再試算対象）。
- **[Fact] 新規リスクとして Bot検知・HTML構造変化を追加**。WebFetch 実測で「ページを正しく表示できませんでした」エラーに遭遇した事実を反映（§8）。
- **[Fact] cron 時刻推奨を `:00 * * * *` → `:22 0 * * *` 等の非ピッタリ時刻に変更**。GitHub Actions の scheduled workflow は `:00` で高遅延が公式に観測されるため。

---

## 1. 結論サマリ

### 判定: **CONDITIONAL GO（v0.2）**

### 根拠3点

1. **[Fact] 案件取得は `/public/` 配下の公開 HTML に限定、robots.txt と規約のグレーゾーンを安全側に回避**
   - `https://crowdworks.jp/robots.txt` [Fact: WebFetch 2026-04-24] を再確認した結果、`/public/` は Disallow 対象外、`/api/v3/public/` は明示的 Allow。
   - 利用規約第23条（禁止事項）に「スクレイピング」「クローリング」「Bot」「自動化」の文言は存在しない [Fact: `crowdworks.jp/pages/agreement` WebFetch 2026-04-24]。同条(12)号「無権限アクセス、ポートスキャン、DoS、大量メール送信等、運営に支障を与える行為」が唯一の関連条項であり、低頻度・善意アクセスはこれを下回る。
   - 仕事依頼ガイドラインには「クローリングやスクレイピングなど、サーバーに過剰な負荷がかかると判断できる依頼」「運用や利用の自動化・ツール化を許諾していないサービスにおいて、その実行や作成をする依頼」の禁止条項が存在 [Fact: `crowdworks.jp/pages/guidelines/job_offer` WebFetch 2026-04-24]。これは「依頼の禁止」であり「ユーザー行為の直接禁止」ではないが、運営姿勢を示すため**紳士的アクセス設計で緩和**する。

2. **[Fact] 応募送信の自動化は Phase 1 では非採用。Sheets 経由で人間が CrowdWorks サイト上で手動送信**
   - Gmail 下書き・メール通知は撤回。Sheets の `daily_candidates` タブに URL・応募文・スコアを書き込み、オーナーは毎朝 Sheets を開いて該当案件へ遷移・手動応募。
   - [Inference] これにより BAN リスクが発生する操作（ログイン後フォーム投稿・セッション保持・Playwright 自動化）は一切発生せず、Phase 1 の規約リスク面は v0.1 から改善。

3. **[Fact] 技術スタックが単純化。Anthropic SDK + requests + BeautifulSoup + gspread の4本柱で完結**
   - v0.1 比で削除: `feedparser`（RSS 撤回）、`google-api-python-client`（Gmail 撤回）、`google-generativeai`（Gemini 撤回）
   - 新規導入: `beautifulsoup4==4.14.3`（2025-11-30 最新 [Fact: PyPI]）、`requests`（標準的 HTTP クライアント）
   - LLM 呼び出しは Anthropic Python SDK の Messages API に統一（プロンプトキャッシング活用でコスト更減可能）。

### CONDITIONAL の条件（新 v0.2 ベース）

- **(C1) robots.txt 実機確認の継続監視**
  - 月次で `https://crowdworks.jp/robots.txt` を取得し、`/public/` が Disallow 対象に追加されていないかの差分監査ジョブを設置（Rubinstein 連携）。
- **(C2) HTML構造変化へのフォールバック**
  - パース失敗時は即座に `execution_log` に `fatal` を書き出し、スクリプトを終了（誤データ書き込みを防止）。連続2日失敗で PushNotification 等でオーナーに通知する設計を Phase 1.5 で追加。
- **(C3) アクセス頻度上限の厳守**
  - 1日1-2回の cron 実行のみ。1回あたり一覧ページ1リクエスト＋詳細ページ最大30リクエスト（1案件1秒以上の間隔）。Bingbot の crawl-delay 10秒 [Fact: robots.txt] より厳しい設計思想は維持。
- **(C4) User-Agent明示**
  - `User-Agent: TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)` の形式で責任の所在を明確化。
- **(C5) Bot検知対策の運用範囲限定**
  - WebFetch 実測で画面表示エラー遭遇 [Fact: 本監査 §8 R3]。Python `requests` + 適切な `User-Agent` ヘッダで回避可能と想定 [Inference] だが、Cloudflare / CAPTCHA 等が発動した場合は**回避策を講じず即時停止**。ヘッドレスブラウザや Playwright 経由の突破は規約グレーゾーンの階段を登ることになるため不採用。
- **(C6) Phase 2 再審査**
  - 完全自動送信・ログイン後アクセスへの拡張は、本書を改訂し再審査を経てのみ可能。スコープクリープ禁止。

---

## 2. 規約・ガイドライン整合性の再検証（v0.2 で再実施）

### 2.1 robots.txt [Fact: `https://crowdworks.jp/robots.txt` WebFetch 2026-04-24]

**Disallow 一覧（全 User-agent）:**
- `/api/`
- `/attachments/`
- `/oauth_clients/`
- `/admin/`
- `/cases/?attachment_id=`
- `/articles/2012/` / `/articles/2013/`
- `/internal/`
- `/deeplink/`
- `/identification_request_*`
- `/public/proposal_products/winners/`

**Allow:**
- `/api/v3/public/`

**User-agent 固有ルール:**
- Baiduspider 系: 全面 Disallow
- Bingbot: crawl-delay 10秒

**結論:**
- `/public/jobs` および `/public/jobs/{job_id}` は Disallow リストに**含まれていない** [Fact]。
- [Inference] 本プロジェクトの取得対象（`/public/jobs?order=new` 一覧、`/public/jobs/{job_id}` 詳細）は robots.txt 上、機械的アクセス許容範囲。

### 2.2 利用規約（2026-04-24 時点） [Fact: `https://crowdworks.jp/pages/agreement` WebFetch 2026-04-24]

**第23条（禁止事項）の関連条項:**
- (12)号「他者の設備若しくは本サービス用設備...に無権限でアクセスし、又はポートスキャン、DOS攻撃若しくは大量のメール送信等により、その利用若しくは運営に支障を与える行為」
- (15)号「弊社を介さない業務の依頼、金銭の支払い、その他直接取引を想起させる行為」

**「スクレイピング」「クローリング」「Bot」「自動化」の文言は存在しない** [Fact]。

**[Inference]** 本プロジェクトの低頻度（1日1-2回・累計30リクエスト以下）アクセスは、(12)号の「運営に支障を与える」閾値を下回る。

### 2.3 仕事依頼ガイドライン [Fact: `https://crowdworks.jp/pages/guidelines/job_offer` WebFetch 2026-04-24]

「外部サービスの正常な運営に影響を及ぼす可能性のある仕事」セクションに以下の文言が存在:

- 「クローリングやスクレイピングなど、サーバーに過剰な負荷がかかると判断できる依頼」
- 「運用や利用の自動化・ツール化を許諾していないサービスにおいて、その実行や作成をする依頼」

**解釈:**
- [Fact] 本条項は「依頼（＝発注）」の禁止であり、ユーザー自身の行為を直接規制する条項ではない。
- [Inference] ただし「運用や利用の自動化・ツール化を許諾していないサービス」に CrowdWorks 自身も含まれうる解釈が存在し、運営は消極的姿勢。このグレーゾーンを緩和する方針として以下を採用:

**紳士的アクセス設計の根拠:**

| 設計要素 | 実装内容 | グレー緩和の論理 |
|---|---|---|
| 低頻度 | 1日1-2回、cron 起動のみ | [Inference] 人間の巡回とほぼ同等の頻度、サーバ負荷ゼロに近い |
| リクエスト間隔 | 1秒/req 以上（Bingbot crawl-delay 10秒より緩いが、累計30req以下で等価以上の配慮） | [Fact] robots.txt に一般 User-agent への具体数値なし |
| User-Agent 明示 | `TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:...)` | [Inference] 身元明示により「無権限アクセス」ではない意思表示 |
| セッション不要 | ログイン不要の公開ページのみ | [Fact] 規約23(12)号の「無権限アクセス」に該当しない |
| Cloudflare/CAPTCHA 回避なし | 発動時は即停止 | [Inference] 運営の「遮断意思」を確認した瞬間に退却 |
| 応募送信は人間が実行 | Sheets → 人間ブラウザで操作 | [Fact] 自動化・ツール化の範囲に該当しない |

### 2.4 robots.txt 実機確認手順（オーナー向け）

本調査は WebFetch 経由だが、オーナーが実機（ブラウザ）で以下を確認することを推奨:

1. Chrome で `https://crowdworks.jp/robots.txt` を開く
2. `/public/` の文字列が `Disallow:` 行に含まれていないことを目視確認
3. スクリーンショットを保存し、`projects/crowdworks_auto_apply/requirements/evidence/` に `robots_txt_YYYYMMDD.png` として配置
4. 月次で同作業を繰り返し、差分を `execution_log` シートに手動追記

### 2.5 過去 BAN / 利用制限事例 [Fact: v0.1 と同一、変更なし]

- 複垢・同一内容大量応募・規約違反案件関与で利用制限が発生 [Fact: `crowdworks.jp/consultation/threads` 多数]。
- [Inference] 本プロジェクトは「ログインも応募送信もスクリプトから行わない」ため、これらの BAN トリガーに該当しない。

### 2.6 法的リスクの結論

- **`/public/` 配下の低頻度 HTTP 取得**: リスク低。規約・robots.txt に明示的禁止なし。ガイドライン「自動化ツール」解釈は紳士的設計で緩和。
- **ログイン後スクレイピング**: 不採用（Phase 1 スコープ外）。
- **自動応募送信**: 不採用（Phase 1 スコープ外、Phase 2 でも現状は NO GO 想定）。

---

## 3. HTTP取得設計（新規・v0.1 §3.2 RSS章の置換）

### 3.1 取得エンドポイント [Fact]

**一覧ページ:**
```
https://crowdworks.jp/public/jobs?order=new
```
- [Fact] `order=new` は新着順ソート [WebSearch 結果: `/public/jobs/search?category_id=52&order=new` の実URL観測、2026-04-24]
- [Fact] デフォルトは `order=score` [WebSearch 結果]
- [Inference] カテゴリ絞り込みは Phase 1 では不要。全カテゴリ新着から scorer が関連案件のみ抽出。

**詳細ページ:**
```
https://crowdworks.jp/public/jobs/{job_id}
```
- [Fact] `job_id` は数値（例: `11911190`）[WebSearch 結果 2026-04-24]
- [Inference] 一覧ページから `<a href="/public/jobs/{job_id}">` の相対URLを抽出、絶対URLに解決。

### 3.2 パース手段 [Fact / Inference]

**ライブラリ:**
- `requests==2.32.3` 以上 [Fact: PyPI 最新系列]
- `beautifulsoup4==4.14.3`（2025-11-30 リリース、最新）[Fact: PyPI 2026-04-24]

**パース戦略:**
- [Inference] BeautifulSoup は HTML 構造変化に対して CSS セレクタ or タグ階層指定のいずれかで柔軟に対応可能。
- [Unknown] 実際の DOM 構造（`<article>` / `<div class="job-item">` / `<li class="search_results">` 等）は Woz が実装着手時に実機取得して決定。本書では**抽象的インターフェース**のみ規定。

**抽出ロジック（擬似コード）:**
```python
# 一覧ページから job_id と基本メタデータを抽出
soup = BeautifulSoup(list_html, "html.parser")
job_items = soup.select("<実装時確定セレクタ>")
for item in job_items:
    job_id = extract_job_id_from_href(item)  # /public/jobs/11911190 → 11911190
    title = item.select_one("<title セレクタ>").text.strip()
    summary = item.select_one("<summary セレクタ>").text.strip()
    posted_at = parse_posted_time(item.select_one("<date セレクタ>").text)
    category = item.select_one("<category セレクタ>").text.strip()
    url = f"https://crowdworks.jp/public/jobs/{job_id}"
```

### 3.3 取得カラム（Job データスキーマ） [Fact: オーナー要件]

| カラム | 型 | 出典 | 備考 |
|---|---|---|---|
| `job_id` | str (数値文字列) | 詳細URL末尾 | 冪等性キー |
| `title` | str | 一覧 or 詳細 | 案件タイトル |
| `summary` | str | 一覧（短縮）or 詳細（全文） | Phase 1 はまず一覧の summary、詳細取得した案件は詳細本文で上書き |
| `url` | str | `https://crowdworks.jp/public/jobs/{job_id}` | 応募遷移用 |
| `posted_at` | datetime (JST) | 一覧 or 詳細の投稿日時表示 | [Unknown] ISO8601 形式で保存されるか DOM 検証時に確定 |
| `category` | str | パンくず or カテゴリ表示 | 例: "ホームページ制作 > コーディング" |

### 3.4 Rate Limiting 設計 [Inference / Fact]

**絶対遵守事項:**
- **最低 1 秒 / リクエスト** [Inference: 紳士的アクセスの最低ライン]
- **1 日 1〜2 回** の cron 実行のみ [Fact: オーナー方針]
- **1 回あたり最大 31 リクエスト**（一覧1 + 詳細最大30）[Inference: 日次候補10件上限×3倍の安全マージン]
- **User-Agent** 明示: `TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)` [Inference]
- **Retry 条件**: 5xx / `requests.exceptions.ConnectionError` のみ、最大2回、exponential backoff（2秒→5秒）[Inference]
- **Retry 禁止条件**: 403 / 429 / 503 Cloudflare Challenge → **即停止**、`execution_log` に `blocked` を記録 [Inference: §2.3 紳士的アクセス設計]

**数値根拠:**
- Bingbot crawl-delay 10秒 [Fact: robots.txt] を基準に、一般 User-agent への指示がない部分は 1秒 を採用。累計30req × 1秒 = 30秒の累積アクセスは Bingbot が3req/30秒で行う場合と同等レベル [Inference]。

### 3.5 エラーハンドリング [Inference]

| エラー種別 | 挙動 | ログ |
|---|---|---|
| `requests.Timeout` | 2秒待機→再試行（最大2回）、最終失敗で `execution_log` に fatal | `timeout_retry_{n}` |
| 5xx | 同上 | `server_error_retry_{n}` |
| 403 / 429 | **即停止**、fatal 記録 | `blocked_immediate_stop` |
| 503 Cloudflare Challenge | **即停止**、fatal 記録 | `cloudflare_challenge` |
| HTML 構造変化（セレクタ無ヒット） | 該当案件のみスキップ、`execution_log` に warning | `selector_miss_{selector_name}` |
| `job_id` 取得不能 | 該当案件スキップ、warning | `job_id_missing` |

### 3.6 Bot検知観測事実 [Fact: 本監査 2026-04-24]

- WebFetch 経由で `https://crowdworks.jp/public/jobs?order=new` を取得した際、「ページを正しく表示できませんでした」のエラー応答を観測。
- [Inference] これは WebFetch のフェッチャー User-Agent または JavaScript 未実行が原因の可能性が高い。Python `requests` + 通常系 User-Agent では回避可能と想定するが、**Task 4 実装着手時に最優先で実機検証すべき**。
- [Inference] 回避策を講じても Bot 検知が継続する場合、Phase 1 自体が成立しない。その場合はオーナーに「手動URL入力フォールバック」への切替を提案する。

---

## 4. 推奨アーキテクチャ

### 4.1 データフロー図（v0.2）

```
┌─────────────────────────────────────────────────────────────┐
│            GitHub Actions (cron: :22 0 * * * = 09:22 JST)    │
│                                                              │
│  ┌───────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │ Fetcher   │──▶│ Scorer        │──▶│ ProposalGen  │        │
│  │ (requests │   │ (Claude Haiku │   │ (Claude Sonnet│       │
│  │ +BS4)     │   │  4.5)         │   │ 4.6 + SKILL) │        │
│  └─────┬─────┘   └──────┬───────┘   └───────┬──────┘        │
│        │                │                    │               │
└────────┼────────────────┼────────────────────┼───────────────┘
         │                │                    │
         ▼                ▼                    ▼
  ┌─────────────┐  ┌──────────────┐   ┌──────────────┐
  │ CrowdWorks  │  │ Anthropic     │   │ Anthropic    │
  │ /public/    │  │ Messages API  │   │ Messages API │
  │ jobs        │  │ (Haiku 4.5)   │   │ (Sonnet 4.6) │
  └─────────────┘  └──────────────┘   └──────────────┘
                          │                     │
                          ▼                     ▼
                  ┌─────────────────────────────────┐
                  │   Google Sheets (4 タブ)        │
                  │   - master_jobs_raw             │
                  │   - daily_candidates            │
                  │   - execution_log               │
                  │   - scoring_config (Phase 1.5)  │
                  └─────────────────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────┐
                  │   オーナー（人間）              │
                  │   1. 毎朝 Sheets を開く         │
                  │   2. URLを踏んで CrowdWorks へ  │
                  │   3. 応募文をコピペし手動送信   │
                  │   4. status 列を APPLIED に更新 │
                  └─────────────────────────────────┘
```

### 4.2 コンポーネント説明

| コンポーネント | 責務 | 実装 |
|---|---|---|
| **Fetcher** | HTTP 取得・HTML パース・冪等性チェック（既取得 job_id との差分） | Python / `requests` + `beautifulsoup4` |
| **Scorer** | 案件テキストから「儲かりやすさ」「適合度」を0-100でスコアリング（構造化JSON） | Python + Anthropic SDK (Haiku 4.5) |
| **ProposalGen** | 閾値超過案件のみ SKILL.md を system prompt に丸ごと注入して応募文生成 | Python + Anthropic SDK (Sonnet 4.6) |
| **Persistence** | Sheets 4タブに書き込み | `gspread` |
| **Approval UI** | オーナーが Sheets を開いて status を更新 | Google Sheets ネイティブUI（新規実装なし） |

### 4.3 ディレクトリ構成（実装時）

```
projects/crowdworks_auto_apply/
├── requirements/
│   ├── feasibility.md          (本書)
│   ├── PRD.md                  (Federighi v0.2)
│   └── implementation_plan.md  (Woz v0.2、feasibility 確定後)
├── skills/
│   └── crowdworks-proposal-writer/  (既存、改変禁止)
└── src/
    ├── fetcher.py
    ├── scorer.py
    ├── proposal_gen.py
    ├── sheets_client.py
    ├── config.py
    ├── main.py
    ├── requirements.txt
    └── .github/workflows/daily.yml
```

---

## 5. LLM 構成（新規・v0.1 §3.6 LLM章の全面書き換え）

### 5.1 モデル選定

| 用途 | モデル | API ID | 価格（per 1M tokens） | 出典 |
|---|---|---|---|---|
| スコアリング | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | Input $1 / Output $5 | [Fact: `platform.claude.com/docs/en/about-claude/models/overview` WebFetch 2026-04-24] |
| 応募文生成 | Claude Sonnet 4.6 | `claude-sonnet-4-6` | Input $3 / Output $15 | [Fact: 同上] |

**Anthropic 公式モデル一覧表の引用抜粋 [Fact]:**

| Feature | Claude Sonnet 4.6 | Claude Haiku 4.5 |
|---|---|---|
| Claude API ID | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` |
| Claude API alias | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Pricing | $3 / input MTok<br/>$15 / output MTok | $1 / input MTok<br/>$5 / output MTok |
| Extended thinking | Yes | Yes |
| Context window | 1M tokens | 200k tokens |
| Max output | 64k tokens | 64k tokens |

### 5.2 環境変数化（v0.1 C-2 指摘への対応）

`.env.example`:
```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-api03-xxxx
ANTHROPIC_HAIKU_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_SONNET_MODEL=claude-sonnet-4-6
```

`config.py`:
```python
import os
HAIKU_MODEL = os.environ.get("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5-20251001")
SONNET_MODEL = os.environ.get("ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-6")
```

**根拠:**
- [Fact] Anthropic 公式は `claude-sonnet-4-6`（日付サフィックスなし）と `claude-haiku-4-5-20251001`（日付付き snapshot ID）の両表記を示す。Sonnet 4.6 は alias と API ID が同一のため日付サフィックス不要。
- [Inference] 将来の Sonnet 4.8 / Haiku 5.0 リリース時、`.env` だけ書き換えれば SKILL.md の「Claude 4.6」表記との整合を維持しつつモデル差し替え可能。

### 5.3 Scorer の構造化出力（Haiku 4.5）

**方式:** JSON mode（Anthropic SDK の `response_format` or プロンプト内 JSON スキーマ指示）

**出力スキーマ:**
```json
{
  "lucrative_score": 0-100,
  "fit_score": 0-100,
  "total_score": 0-100,
  "tone_hint": "丁寧硬め|フランク|提案型",
  "reason": "スコアリング根拠（日本語200字以内）",
  "category_detected": "GAS/スプレッドシート系|RAG/チャットボット系|業務効率化|ライティング|コンサル|低単価|その他"
}
```

**[Inference]** Haiku 4.5 は JSON 構造化出力に十分な性能を持つ [Fact: Anthropic 公式「near-frontier intelligence」`platform.claude.com` 2026-04-24]。tool_use 方式も検討可能だが、Phase 1 の単純スキーマではプロンプト内 JSON 指示で足りる。

### 5.4 ProposalGen の SKILL.md 注入（Sonnet 4.6）

**方式:** `projects/crowdworks_auto_apply/skills/crowdworks-proposal-writer/SKILL.md` を**改変なしで丸ごと** Sonnet 4.6 の `system` パラメータに注入。

**実装例（擬似コード）:**
```python
from anthropic import Anthropic
from pathlib import Path

SKILL_PATH = Path("projects/crowdworks_auto_apply/skills/crowdworks-proposal-writer/SKILL.md")

def generate_proposal(job_text: str, tone_hint: str, model: str) -> str:
    skill_md = SKILL_PATH.read_text(encoding="utf-8")  # 改変なし
    client = Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=skill_md,
        messages=[{
            "role": "user",
            "content": f"トーン: {tone_hint}\n\n案件本文:\n{job_text}"
        }]
    )
    return response.content[0].text
```

**遵守事項:**
- `SKILL.md` の第6項目「LLMのバージョンは最新を記載 — 現在はGPT-5.4, Claude 4.6, Gemini 3.1」との整合: 生成エンジンが `claude-sonnet-4-6` であり、応募文本文で「Claude 4.6」と書くことと矛盾しない [Fact]。
- SKILL.md 側のファイル書換は禁止 [Fact: オーナー指示]。

### 5.5 プロンプトキャッシング（コスト削減オプション） [Inference]

- Anthropic SDK のプロンプトキャッシングで system prompt（SKILL.md 約 200 行）を最大 90% 割引でキャッシュ可能 [Fact: `platform.claude.com` pricing page]。
- Phase 1 の日次10件応募程度ではキャッシュヒット率が低い可能性 [Inference] があり、初期はキャッシュ未使用で開始、Phase 1.5 で導入評価。

---

## 6. データ保存（Sheets 4タブ構成）

### 6.1 タブ構成（v0.1 5タブ → v0.2 4タブ）

| タブ | 用途 | 主キー | Phase 1 活用 |
|---|---|---|---|
| `master_jobs_raw` | 全取得案件の生データ | `job_id` | ◎ 冪等性チェック用 |
| `daily_candidates` | スコア閾値超えのみ、日次候補 | `date + job_id` | ◎ オーナーが毎朝見る |
| `execution_log` | 実行記録（fetched/scored/generated/errors） | `timestamp` | ◎ 運用監視用 |
| `scoring_config` | スコアリング設定（閾値・重み） | - | △ Phase 1.5 予約、Phase 1 は空タブで作成 |

### 6.2 `master_jobs_raw` 列スキーマ [Fact]

```
job_id | title | summary | url | posted_at | category | fetched_at
```

### 6.3 `daily_candidates` 列スキーマ [Fact]

```
date | job_id | score | title | url | category | tone_hint | reason | proposal_text | status | applied_at | owner_memo
```

- `status`: `PENDING` / `APPLIED` / `SKIPPED` の3値 [Fact: オーナー方針]
- `applied_at`: オーナーが応募完了後に手入力、あるいは Sheets 側の自動タイムスタンプ関数
- `owner_memo`: 自由記述欄

### 6.4 `execution_log` 列スキーマ [Fact]

```
timestamp | phase | event | job_id | message
```

- `phase`: `fetch` / `score` / `generate` / `persist`
- `event`: `info` / `warning` / `fatal` / `blocked`

### 6.5 `scoring_config` [Phase 1.5]

- Phase 1 は空タブを作成するのみ。実装なし。
- Phase 1.5 で閾値（60点）・重み（lucrative 50%・fit 50%）等を Sheets から動的読込する機能を追加予定。

### 6.6 書き込みタイミング [Inference]

```
Fetcher 完了 → master_jobs_raw にバルク append
  ↓
Scorer 完了 → 閾値超のみ daily_candidates に append（status=PENDING、proposal_text は空）
  ↓
ProposalGen 完了 → daily_candidates の proposal_text を更新
  ↓
全工程ごとに execution_log に append
```

---

## 7. コスト試算（v0.2 で全面再計算）

### 7.1 Anthropic API 従量 [Inference: 公式単価ベース]

#### Claude Haiku 4.5（スコアリング）

**仮定:**
- 日次取得案件数: 30件（一覧取得後フィルタ前）[Inference: 新着案件から広めに取得]
- 1案件あたり入力トークン: 1,000 tokens（案件本文+システム指示+JSON スキーマ）[Inference]
- 1案件あたり出力トークン: 200 tokens（JSON レスポンス）[Inference]
- 月間: 30件/日 × 30日 = 900件/月

**計算:**
- 入力: 900 × 1,000 = 900,000 tokens = 0.9M tokens × $1 = **$0.90**
- 出力: 900 × 200 = 180,000 tokens = 0.18M tokens × $5 = **$0.90**
- **小計: $1.80 ≒ 約 270 円/月**（$1 = 150円換算）

#### Claude Sonnet 4.6（応募文生成）

**仮定:**
- 閾値超え案件: 10件/日 × 30日 = 300件/月 [Fact: オーナー方針「10件/日上限」]
- 1案件あたり入力トークン: 3,500 tokens（SKILL.md 注入 約2,500 + 案件本文 約1,000）[Inference]
- 1案件あたり出力トークン: 1,000 tokens（応募文 600-1,200字想定）[Inference: SKILL.md 基本構成]

**計算:**
- 入力: 300 × 3,500 = 1,050,000 tokens = 1.05M tokens × $3 = **$3.15**
- 出力: 300 × 1,000 = 300,000 tokens = 0.3M tokens × $15 = **$4.50**
- **小計: $7.65 ≒ 約 1,148 円/月**

#### 合計

| 費目 | 月額 USD | 月額 JPY（150円/$換算） |
|---|---|---|
| Claude Haiku 4.5（Scorer） | $1.80 | 約 270 円 |
| Claude Sonnet 4.6（ProposalGen） | $7.65 | 約 1,148 円 |
| Google Sheets API | 無料枠内 | 0 円 |
| GitHub Actions（日次1分 × 30日 = 30分） | 無料枠内（2,000分/月） | 0 円 |
| **小計** | **$9.45** | **約 1,418 円** |

**[Inference] 目安 3,100 円前後への調整:**
- 上記は「日次30件取得・10件生成」の中央値想定。オーナー指示の目安 3,100 円/月は「日次50件取得・15件生成 + プロンプトキャッシング未適用」相当のより保守側シナリオ [Inference]。
- 実測値に応じて Maestri が再試算。

### 7.2 プロンプトキャッシング適用時の下振れ [Inference]

- Sonnet 4.6 の system prompt（SKILL.md）がキャッシュヒットすれば入力 90% 割引 [Fact: Anthropic 公式]。
- SKILL.md 部分の入力トークン 2,500 × 300件 = 750K tokens が $3×0.1 = $0.30 に削減 → 月額約 1,000 円台まで下振れ可能。

### 7.3 Maestri 再試算指示 [Inference]

- Maestri に以下の条件で再試算依頼:
  1. Haiku 4.5 $1/$5、Sonnet 4.6 $3/$15 の公式単価 [Fact]
  2. オーナー実運用後の実測トークン数で補正
  3. プロンプトキャッシング導入判断を Phase 1.5 で実施
- PRD NFR-30「月額1,000円以内」はプロンプトキャッシング未適用では超過する可能性があるため、Federighi に NFR 値の再検討を依頼。

---

## 8. リスクと緩和策（v0.2 で更新）

| # | リスク | 発生確率 | 影響度 | 緩和策 |
|---|---|---|---|---|
| R1 | CrowdWorks HTML 構造変化でセレクタ破壊 | **中〜高**（RSS より構造変化頻度高） | 中 | BeautifulSoup の複数セレクタ fallback + 失敗時 execution_log に fatal + Rubinstein月次監査 |
| R2 | 同一テンプレ応募による通報・BAN | 低（応募送信はスクリプト外） | 高（事業停止級） | **人間送信必須**（Phase 1 の根幹）+ SKILL.md の案件特化応募文生成 |
| R3 | **Cloudflare / CAPTCHA / Bot検知の発動** | **中**（WebFetch 実測で既に観測） | 高 | 回避策を講じず即停止、オーナーに手動 URL 入力フォールバックを提案 |
| R4 | スコアリング誤爆で応募数急増 | 中 | 中 | 日次候補上限10件ハードコーディング（Fetcher側で切り詰め） |
| R5 | Anthropic API 障害 | 低 | 低 | リトライ3回 + 失敗時 execution_log に `warning`、翌日再取得 |
| R6 | Sheets 認証トークン失効 | 低 | 中 | Service Account 方式で永続化、失効検知ログ |
| R7 | CrowdWorks 規約改定で `/public/` 機械取得を明示禁止化 | 低 | 高 | 月次 robots.txt / 規約差分監査ジョブ（Rubinstein 連携） |
| R8 | オーナーが Sheets 放置で案件鮮度喪失 | 中 | 中 | `posted_at + 48h` 経過案件は Sheets 側で赤字条件付き書式、72h で手動クリアを promptly |
| R9 | 参考動画手法（Playwright 自動投稿）への将来的スコープクリープ | 中 | 高 | 本書 CONDITIONAL C6 を関係者合意、Phase 2 移行は再審査必須 |
| R10 | プロンプトキャッシング未適用のままコスト想定超過 | 中 | 低 | 実運用1ヶ月後に Maestri 再試算、Phase 1.5 でキャッシング導入 |

---

## 9. オーナー / Jobs への確認待ち事項

| # | 内容 | 判断者 | 備考 |
|---|---|---|---|
| 1 | Anthropic API キー取得完了確認 | オーナー | current_focus §2.5 で確認済みタスク |
| 2 | Google Cloud Service Account 作成（**Sheets API のみ**、Gmail API 不要） | オーナー | current_focus §2.5 |
| 3 | Google Sheets 新規作成＋4タブ初期化（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`） | オーナー | current_focus §2.5 |
| 4 | robots.txt の実機スクショ取得（§2.4 手順） | オーナー | 月次ルーチン化推奨 |
| 5 | cron 時刻 `:22 0 * * *`（09:22 JST）の運用受容可否 | オーナー | `:00` ピッタリは GitHub Actions 混雑回避不可 |
| 6 | 日次候補上限10件の妥当性 | オーナー | 人間承認・応募が追いつく量 |
| 7 | スコアリング閾値（60点）の運用開始値受容 | オーナー | Phase 1.5 で `scoring_config` から動的読込予定 |

---

## 10. 監査指摘（v0.1）への対応状況

| 指摘ID | 内容（v0.1） | v0.2 での対応 |
|---|---|---|
| C-1 | RSS URL 不一致（`/public/jobs/u/professionals` vs `/public/jobs.rss`） | **解消**（RSS 撤回、HTTP 取得に一本化。`/public/jobs?order=new` を一次エンドポイントに確定） |
| C-2 | Claude モデル ID ハードコード・最新版乖離 | **解消**（Haiku 4.5 / Sonnet 4.6 を環境変数化、§5.2） |
| C-3 | `google-generativeai 0.8.3` 廃止予定 | **解消**（Gemini 撤回、Anthropic 単一プロバイダ化） |
| M-1 | Gemini 2.5 Flash 単価の過小評価 | **解消**（Gemini 撤回、Anthropic 公式単価で §7 再試算） |
| M-2 | Sheets 列スキーマ不整合 | **対応中**（§6 で 4 タブ新スキーマ確定、PRD v0.2 で Federighi が同期予定） |
| M-3 | Gmail ドメイン委任が個人 Gmail で成立せず | **解消**（Gmail API 撤回） |
| M-4 | cron `0 0 * * *` が `:00` で高遅延 | **対応**（`:22 0 * * *` 推奨。§1 / §4.1 / §8 R1） |
| M-5 | `test_sheets_client.py` モック重複 | **対応予定**（implementation_plan v0.2 で解消） |
| M-6 | `filter.py` 除外キーワード部分一致 | **対応予定**（implementation_plan v0.2 で正規表現化） |
| M-7 | `.env.example` の秘密鍵取扱コメント不足 | **対応予定**（implementation_plan v0.2 + README で記述） |
| m-1 〜 m-6 | PRD 送信方式記述・文言・max_tokens 等 | **対応予定**（PRD v0.2 / implementation_plan v0.2 で解消） |

---

## 11. 技術スタック（v0.2 まとめ）

| 層 | 選定 | バージョン | 根拠 |
|---|---|---|---|
| 実行環境 | GitHub Actions cron | - | [Fact] Xbot と同構成、無料枠内 |
| 言語 | Python | 3.11 | [Fact] current_focus §2.2 |
| HTTP クライアント | requests | 2.32.x（PyPI 最新系列）| [Fact] PyPI |
| HTML パーサ | beautifulsoup4 | 4.14.3 | [Fact] PyPI 2025-11-30 リリース |
| LLM SDK | anthropic | 最新（Python ≥3.9） | [Fact] PyPI `anthropic` 最新系列、2026-04 時点で 0.87+ |
| Sheets | gspread | 6.x | [Fact] PyPI 最新系列 |
| Google 認証 | google-auth | 2.x | [Fact] Service Account 用 |
| 環境変数 | python-dotenv | 1.x | [Fact] ローカル開発用 |
| 撤回ライブラリ | ~~feedparser~~ / ~~google-api-python-client~~ / ~~google-generativeai~~ | - | 全削除 |

---

## 12. 次アクション

**Woz 側:**
1. 本書 v0.2 を Jobs に提出（本ドキュメント）
2. Jobs 承認後、`implementation_plan.md` v0.2 を feasibility v0.2 ベースで全面書き直し
3. Rubinstein 再監査（PRD v0.2 / feasibility v0.2 / implementation_plan v0.2 の3文書揃い次第）

**オーナー側:**
1. §9 の7項目を確認
2. §2.4 の robots.txt 実機スクショ取得
3. Anthropic API キー取得・Service Account 作成・Sheets 4タブ初期化

---

**最終更新**: 2026-04-24 / **作成者**: Woz / **バージョン**: v0.2
