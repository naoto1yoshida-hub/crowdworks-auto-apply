# オーナー向け環境準備手順書（CrowdWorks 自動応募システム v0.3）

**バージョン**: v0.3
**更新日**: 2026-04-26
**作成者**: Woz (CTO)
**対象**: オーナー（吉田尚人）
**所要時間目安**: 60〜90 分

---

## 0. 結論ファースト（このページで何をするか）

実装着手の前にオーナー側で以下 4 件を完了させる。所要 60〜90 分。

1. **GCP Service Account 作成**（Sheets API のみ有効化、JSON キー取得）
2. **Google Sheets 新規作成 + 4 タブ初期化**（列スキーマは本書 §3 確定版を使用）
3. **Service Account に Sheets を共有**（編集権限）
4. **GitHub Secrets 登録**（API キー / SA JSON / Spreadsheet ID 等）

すべて完了したら Jobs に「準備完了」と一言伝えれば、Woz が Task 2 から実装着手します。

---

## 1. GCP Service Account 作成

### 1.1 GCP プロジェクト作成（既存プロジェクトがあれば 1.2 から）

1. ブラウザで `https://console.cloud.google.com/` を開く
2. 上部のプロジェクト選択メニュー → 「新しいプロジェクト」
3. プロジェクト名: `tegg-crowdworks-auto-apply`（任意の識別可能な名前）
4. 「作成」を押下、プロジェクト切替完了を待つ

[Screenshot: GCP コンソール プロジェクト作成画面]

### 1.2 Sheets API のみ有効化（Gmail API は不要）

1. 左サイドバー「API とサービス」→「ライブラリ」
2. 検索ボックスに `Google Sheets API` と入力
3. 「Google Sheets API」を選択 → 「有効にする」を押下
4. **Gmail API は v0.3 設計から完全撤回したため有効化不要**

[Screenshot: Sheets API 有効化画面]

### 1.3 Service Account 作成

1. 左サイドバー「API とサービス」→「認証情報」
2. 「+ 認証情報を作成」→「サービスアカウント」
3. サービスアカウント名: `crowdworks-auto-apply-sa`（任意）
4. サービスアカウント ID は自動入力されるのでそのまま「作成して続行」
5. ロール選択は **何も付与しない**（Sheets はシート単位で個別共有するため、プロジェクトロールは不要）
6. 「続行」→「完了」

[Screenshot: Service Account 作成完了画面]

### 1.4 JSON キーファイル取得

1. 認証情報画面で作成した Service Account のメールアドレス（`crowdworks-auto-apply-sa@<project-id>.iam.gserviceaccount.com`）をメモする
2. 該当行をクリック → 「鍵」タブ
3. 「鍵を追加」→「新しい鍵を作成」→「JSON」→「作成」
4. ダウンロードされた `<project-id>-xxxxx.json` を **安全な場所に保存**（後で GitHub Secrets と `.env` に使用）
5. このファイル名をローカル開発用に `service_account.json` にリネームし、リポジトリ直下ではなくプロジェクトディレクトリ `projects/crowdworks_auto_apply/` の **外** にコピー、または `.gitignore` 済みのプロジェクト直下に配置

[Screenshot: JSON キーダウンロード画面]

**注意（最重要）:**
- このファイルは API キー相当の機密情報。GitHub には絶対に commit しない（`.gitignore` で `service_account.json` を除外済）
- 誤って commit した場合は **即 Service Account を削除して再生成**

---

## 2. Google Sheets 新規作成と 4 タブ初期化

### 2.1 新規スプレッドシート作成

1. ブラウザで `https://sheets.google.com/` を開く
2. 「+」（空白）から新規作成
3. ファイル名を `crowdworks_auto_apply_v0.3` に変更
4. URL の `/d/` と `/edit` の間にある **Spreadsheet ID** をメモ（例: `1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABC`）

[Screenshot: 新規 Sheets URL]

### 2.2 4 タブを作成

デフォルトの「シート 1」を `master_jobs_raw` にリネーム後、下部「+」で残り 3 タブを追加。タブ名は厳密に以下と一致させる（実装が直接参照する）。

| タブ名（厳密一致必須） | 用途 |
|---|---|
| `master_jobs_raw` | 全取得案件の生データ（冪等性キー: job_id） |
| `daily_candidates` | 60 点以上の応募候補（オーナーの作業画面、上限 10 件/日） |
| `execution_log` | 実行ログ（fetch/score/generate/persist の info/warning/fatal/blocked） |
| `scoring_config` | Phase 1.5 予約（Phase 1 ではヘッダのみ） |

### 2.3 ヘッダ列の確定版スキーマ（v0.3 確定）

[Fact] PRD v0.2 F-41（10 列）と implementation_plan v0.2 / feasibility v0.2 §6.3（12 列）の不整合（Rubinstein M-2'）を、**implementation_plan の 12 列基準で v0.3 確定**する。理由は (a) `category` 列は Sheets 上のフィルタ・ソート UX に必須、(b) `owner_memo` 列はオーナーの応募振り返りメモに必要、(c) 実装テスト（`test_append_daily_candidate_writes_12_cols`）が 12 列前提で書かれており、PRD を 12 列側に寄せる方が実装コストが小さいため。Federighi に PRD v0.3 差分発行を依頼予定（Jobs 案件）。

各タブの 1 行目（ヘッダ行）に以下を A1 から横方向に入力する。

#### 2.3.1 `master_jobs_raw`（7 列）

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| `job_id` | `title` | `summary` | `url` | `posted_at` | `category` | `fetched_at` |

#### 2.3.2 `daily_candidates`（12 列、v0.3 確定）

| A | B | C | D | E | F | G | H | I | J | K | L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `date` | `job_id` | `score` | `title` | `url` | `category` | `tone_hint` | `reason` | `proposal_text` | `status` | `applied_at` | `owner_memo` |

- `status` は `PENDING` / `APPLIED` / `SKIPPED` の 3 値
- `applied_at` はオーナーが APPLIED に更新した時刻（手入力 or 数式 `=NOW()` を貼り付け）
- `owner_memo` は自由記述欄

#### 2.3.3 `execution_log`（5 列）

| A | B | C | D | E |
|---|---|---|---|---|
| `timestamp` | `phase` | `event` | `job_id` | `message` |

- `phase`: `fetch` / `score` / `generate` / `persist`
- `event`: `info` / `warning` / `fatal` / `blocked`

#### 2.3.4 `scoring_config`（2 列、Phase 1.5 予約）

| A | B |
|---|---|
| `key` | `value` |

Phase 1 ではデータ行は空のまま（ヘッダのみ）。

### 2.4 手動初期化 vs GAS スクリプトでの一括初期化（任意）

**A. 手動初期化（推奨、所要 10 分）:**
上記 2.1〜2.3 をブラウザで手動入力する。

**B. GAS スクリプトで一括初期化（任意、自動化派向け）:**
スプレッドシートで「拡張機能」→「Apps Script」を開き、以下を貼り付けて実行（初回は権限承認が必要）。

```javascript
function initializeTabs() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const schemas = {
    'master_jobs_raw': ['job_id', 'title', 'summary', 'url', 'posted_at', 'category', 'fetched_at'],
    'daily_candidates': ['date', 'job_id', 'score', 'title', 'url', 'category', 'tone_hint', 'reason', 'proposal_text', 'status', 'applied_at', 'owner_memo'],
    'execution_log': ['timestamp', 'phase', 'event', 'job_id', 'message'],
    'scoring_config': ['key', 'value'],
  };
  Object.keys(schemas).forEach(function (name) {
    var sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    sheet.getRange(1, 1, 1, schemas[name].length).setValues([schemas[name]]);
    sheet.setFrozenRows(1);
  });
  // デフォルト「シート1」を削除（任意）
  var def = ss.getSheetByName('シート1');
  if (def && ss.getSheets().length > 1) ss.deleteSheet(def);
  Logger.log('initialized 4 tabs');
}
```

実行後、4 タブにヘッダが入っていることを目視確認する。

[Screenshot: 4 タブ作成後のスプレッドシート全景]

---

## 3. Service Account に Sheets を共有

1. スプレッドシート右上「共有」ボタン
2. §1.3 でメモした Service Account メール（`crowdworks-auto-apply-sa@<project-id>.iam.gserviceaccount.com`）を入力
3. 権限は **編集者** を選択（実装が `append_row` で書き込むため必須）
4. 「通知」のチェックは外して OK（Service Account にはメールボックスがないため）
5. 「共有」を押下

[Screenshot: 共有設定画面 編集者権限]

**確認:**
- 共有完了後、Sheets を Service Account から API 経由でアクセス可能になる
- ローカルからの初回接続テストは Task 9 完了後に `pytest tests/test_sheets_client.py` で実施

---

## 4. GitHub Secrets 登録

リポジトリの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」で以下を登録する。

| Secret 名 | 値 | 取得元 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | Anthropic Console（取得済） |
| `ANTHROPIC_HAIKU_MODEL` | `claude-haiku-4-5-20251001` | （未登録なら実装デフォルト値が使われる） |
| `ANTHROPIC_SONNET_MODEL` | `claude-sonnet-4-6` | （未登録なら実装デフォルト値が使われる） |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | §1.4 で取得した JSON ファイルの **全文を 1 行化したもの** | ローカルで `cat service_account.json | jq -c .` を実行した結果を貼り付け（jq がない場合は改行を `\n` にエスケープ） |
| `SPREADSHEET_ID` | §2.1 でメモした ID | URL から抽出 |
| `USER_AGENT` | `TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)` | （未登録なら実装デフォルト値） |

**重要:**
- `GOOGLE_SERVICE_ACCOUNT_JSON` は改行エスケープが崩れやすい。GitHub Secrets に貼る前に必ず 1 行化する
- 1 行化が手間な場合は `cat service_account.json` の出力をそのまま貼っても OK だが、実装側で `json.loads` 時に `Expecting value` エラーが出たら 1 行化に切り替える

[Screenshot: GitHub Secrets 登録画面]

---

## 5. ローカル `.env` 設定例（ローカル開発時のみ）

`.env.example` をコピーして `.env` を作成し、自分の値を埋める。`.env` は `.gitignore` 済み。

```bash
cd projects/crowdworks_auto_apply
cp .env.example .env
```

最低限埋めるべき値（他はデフォルトで動作）:

```dotenv
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_SERVICE_ACCOUNT_FILE=./service_account.json
SPREADSHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABC
```

`service_account.json` は §1.4 でダウンロードしたファイルをこのプロジェクト直下に配置（`.gitignore` 済）。

---

## 6. 完了確認チェックリスト

オーナー側で以下を全て確認できたら Jobs に報告。

- [ ] GCP プロジェクトを作成し Sheets API を有効化した
- [ ] Service Account を作成し JSON キーを安全な場所に保存した
- [ ] Google Sheets を新規作成し、4 タブ（`master_jobs_raw` / `daily_candidates` / `execution_log` / `scoring_config`）を本書 §2.3 のヘッダで初期化した
- [ ] Sheets を Service Account メールに編集権限で共有した
- [ ] GitHub Secrets に最低 `ANTHROPIC_API_KEY` / `GOOGLE_SERVICE_ACCOUNT_JSON` / `SPREADSHEET_ID` を登録した
- [ ] ローカル開発を行う場合は `.env` を作成し動作確認できる状態にした

---

## 7. トラブルシュート

### 7.1 Sheets API 401 / 403

- Service Account メールに編集権限が共有されているか §3 を再確認
- Sheets API がプロジェクトで有効化されているか §1.2 を再確認

### 7.2 `gspread.exceptions.APIError: Quota exceeded`

- 無料枠（100 req/100 sec/user）超過の可能性。Phase 1 では日次 1 回起動・上限 10 件のため通常起きない
- 起きた場合は `execution_log` に記録され翌日リトライ

### 7.3 `GOOGLE_SERVICE_ACCOUNT_JSON` パースエラー

- 改行エスケープ崩れが原因。`jq -c .` で 1 行化したものを再登録

### 7.4 誤って `service_account.json` を commit してしまった

- 即 GCP コンソールで該当 Service Account を削除し、新規 SA を作成して JSON を再取得
- GitHub Secrets を新しい JSON で更新
- 旧 SA がコミット履歴に残っても、SA が削除されていれば失効済のため漏洩実害なし（コミット履歴の改竄は不要）

---

最終更新: 2026-04-26 / バージョン: v0.3 / 担当: Woz (CTO)
