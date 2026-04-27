# PRD: CrowdWorks 自動応募システム（Phase 1: 半自動 MVP）

**プロジェクトコード**: crowdworks_auto_apply
**バージョン**: v0.2
**更新日**: 2026-04-24
**改訂者**: Federighi (Head of Product)
**前版**: v0.1 (2026-04-21, Federighi)

---

## 0. エグゼクティブサマリ（結論ファースト）

[Inference] CrowdWorks 新着案件を毎朝 GitHub Actions cron で HTML スクレイピング取得 → Claude Haiku 4.5 でスコアリング → 閾値60点以上を Claude Sonnet 4.6 + 既存 `crowdworks-proposal-writer` スキルで応募文生成 → Google Sheets `daily_candidates` タブに直接書き込む。オーナーは毎朝 Sheets を開き、URL経由で CrowdWorks サイトへ遷移、応募文をコピペして手動送信、status 列を APPLIED へ手動更新する運用。Gmail API・RSS・Gemini は v0.2 で全面撤回。

**北極星指標（KPI）**: [Inference]
- 週間応募本数: 週10〜20件（手動時の3倍、MVP 達成ライン）
- 応募→返信率: 15%以上（月次計測、Phase 1 運用で確定）
- 応募1件あたりのオーナー作業時間: 30分 → 5分（Sheets確認＋コピペ＋手動送信）

---

## 変更概要（v0.1 → v0.2）

v0.3 設計刷新に伴い、以下を改訂した:

1. **Gmail API を全面撤回** — ドメイン委任・下書き作成・通知送信の F-要件と NFR を全削除。成果物は Google Sheets への直接書き込みに統一（Rubinstein M-3 自動解消）。
2. **RSS 取得を撤回** — CrowdWorks 公式 RSS サービスは提供終了を公式ブログで確認（URL 404 済み）。HTML スクレイピング方式へ切替（Rubinstein C-1 自動解消）。
3. **Gemini を全面撤回** — スコアリングも Claude Haiku 4.5 に統一、LLM プロバイダは Anthropic 単一化（Rubinstein C-3/M-1 自動解消）。
4. **運用フローを「オーナー手動送信」に統一** — 半自動ワンクリック送信の記述を全て「オーナーが Sheets の URL に飛び、応募文をコピペして手動送信し、status を APPLIED に更新」に書き換え（Rubinstein m-1 解消）。
5. **Sheets を 5タブ → 4タブに集約** — `draft_proposals` と `sent_log` を `daily_candidates` タブに統合（Rubinstein M-2 解消）。
6. **日次上限を 10件に確定** — v0.1 の 10件記述はオーナー判断で v0.3 正式仕様となる（Rubinstein m-2 解消、Jobs 決定「5件」から 10件 へ緩和の最終決定）。
7. **F-80 実行基盤を GitHub Actions cron に確定** — GAS トリガー選択肢を削除（Rubinstein m-3 解消）。
8. **月額予算目安を 3,100円に更新** — v0.1 は 1,000円だった。Claude 単一プロバイダ化によるコスト構造を反映、Maestri 再試算対象として明記。

---

## 1. 背景・目的（Why）

### 1.1 背景 [Fact]
- オーナー（吉田尚人氏、31歳、京都、製造業法人営業×AIエンジニア副業、週20-30時間稼働）は TEGG Engineering ブランドで CrowdWorks を含む副業プラットフォームから案件を獲得している。
- 既存の `crowdworks-proposal-writer` スキル（`projects/crowdworks_auto_apply/skills/crowdworks-proposal-writer/SKILL.md`）により、案件テキストを貼付すれば応募文生成は既に高品質に自動化されている。
- しかし「新着案件の発見」「案件の取捨選択」「応募文の CrowdWorks フォーム投入」の各工程が手動で、案件取りこぼしとオーナー稼働の逼迫が発生している。
- [Fact] CrowdWorks 公式 RSS 配信サービスは公式ブログ「RSS 配信サービス提供終了のお知らせ」で提供終了が告知されており、`https://crowdworks.jp/public/jobs/u/professionals` は 404 を返すことを 2026-04-24 に確認済み。

### 1.2 目的（Why）[Inference]
1. **キャッシュフロー最優先**: Phase 1 を先に回し、後続プロジェクト（X運用ボット、note マネタイズ）の資金的土台を作る。
2. **オーナーの稼働圧縮**: 新着検索・選定・応募文作成の自動化（送信は手動だが思考コストをゼロに）。
3. **応募品質の一貫性**: 既存スキル絶対ルール10項目（嘘禁止・名前「吉田」固定・LLMバージョン最新・稼働週20-30時間 等）を機械的に遵守。
4. **データ蓄積**: 案件スコア・応募文・結果を Sheets に蓄積し、スコアリング改善とスキル更新のフィードバックループを回す。

### 1.3 対象外（Non-Goals）
- CrowdWorks 以外のプラットフォーム（ランサーズ、ココナラ等）への展開は Phase 3 以降 [Inference]
- 受注後のプロジェクト管理・請求書発行等の後工程
- 完全自動送信（Exit Criteria 達成後に Phase 2 で検討）
- クライアント企業エンリッチ（Phase 1.5 で検討）

---

## 2. スコープ

### 2.1 MVP（Phase 1: 半自動）[Inference]
| 範囲 | 含む / 含まない |
|---|---|
| 新着案件の日次スキャン（GitHub Actions cron） | 含む |
| HTML スクレイピングによる案件取得 | 含む（公開ページ `/public/jobs` からのみ） |
| 案件の正規化・スコアリング（Claude Haiku 4.5） | 含む |
| 既存スキルによる応募文生成（Claude Sonnet 4.6） | 含む（SKILL.md は改変禁止、system prompt 注入のみ） |
| Google Sheets への直接書き込み | 含む（`daily_candidates` タブ上限10件/日） |
| **送信（オーナーが Sheets の URL に遷移 → 応募文コピペ → CW サイトで手動送信 → Sheets の status を APPLIED へ更新）** | **含む（完全手動）** |
| ログ・監査証跡（`execution_log` タブ） | 含む |
| Gmail 通知・Gmail 下書き作成 | **含まない（v0.2 で撤回）** |
| RSS 取得 | **含まない（v0.2 で撤回）** |
| Gemini API | **含まない（v0.2 で撤回）** |
| 完全自動送信 | 含まない（Phase 2） |
| クライアント企業エンリッチ | 含まない（Phase 1.5） |

### 2.2 Phase 2 以降の布石（スコープ外だが設計上考慮）
- 完全自動送信: Exit Criteria（§8）達成後に移行
- スコアリング設定の Sheets 動的読込（Phase 1.5）
- データ蓄積スキーマの共通化

### 2.3 動画参考との差分 [Inference]
参考動画「Claude Codeで月商5000万」は PR TIMES → メール下書き → Gmail 蓄積という一方向構造。v0.2 で Gmail API を撤回した結果、本プロジェクトは Sheets 単一 UI にさらにシンプル化された。オーナーの毎朝のチェックポイントは「Sheets を開く」のみ。

---

## 3. ユーザーストーリー（オーナー視点）

**US-01** [Inference]
> オーナーとして、毎朝 Google Sheets の `daily_candidates` タブを開けば、その日の「吉田さん向き」TOP 10件までの応募文下書きが URL・スコア付きで並んでいる状態にしたい。理由: 案件検索と応募文作成の手作業を丸ごと省略するため。

**US-02** [Inference]
> オーナーとして、応募したい案件の URL をクリックして CrowdWorks サイトに飛び、Sheets の `proposal_text` をコピーして応募フォームに貼り付け、送信後に Sheets の status を PENDING → APPLIED に更新する運用で完結させたい。理由: CrowdWorks 利用規約のグレーゾーン（自動応募の明示的許諾なし）を完全に回避するため。

**US-03** [Inference]
> オーナーとして、応募前に Sheets 上で `proposal_text` を軽く修正（1〜2行の微調整）できるようにしたい。理由: 案件の機微やクライアント特性に応じて最終調整するため。

**US-04** [Inference]
> オーナーとして、過去に応募した案件と結果（返信あり / なし / 成約）を Sheets 上で振り返りたい。理由: スコアリング基準の調整と応募文の改善ループを回すため。

**US-05** [Inference]
> オーナーとして、CrowdWorks 利用規約に違反する挙動（過剰スクレイピング、自動送信）が絶対に発生しないようにしたい。理由: アカウント BAN はキャッシュフロー戦略の根幹を揺るがす最大リスクのため。

---

## 4. 機能要件

### 4.1 案件取得（新着 CW 案件の日次スキャン）
- **F-01** [Inference]: GitHub Actions cron（JST 朝 9 時台、`:00` ピッタリを避けた時刻）で日次スキャンを起動する。
- **F-02** [Inference]: 取得対象は `https://crowdworks.jp/public/jobs` 配下の公開ページ（ログイン不要）。対象カテゴリは「システム開発」「ホームページ制作」「アプリ・スマートフォン開発」「ライティング」「データ処理」配下の AI/Python/GAS/RAG/業務効率化関連タグ（詳細はオープンクエスチョン Q-01）。
- **F-03** [Inference]: 1日あたりのスキャン回数は 1〜2 回に制限。連続スキャン・高頻度ポーリング禁止。
- **F-04（新規）** [Inference]: HTML スクレイピング方式で実装する。HTTP クライアントは Python `requests`、HTML パーサは `BeautifulSoup` を採用。
- **F-05（新規）** [Inference]: **Rate Limiting のハードガード**: リクエスト間隔は 1 秒/req 以上を厳守。詳細ページ巡回時も同ルール適用。
- **F-06（新規）** [Inference]: **robots.txt および利用規約の紳士的遵守**: 実行前に `robots.txt` を取得して Disallow パスへのアクセスを禁止。User-Agent は TEGG Engineering の識別可能な値（例: `TEGG-Engineering-JobScanner/1.0 (contact: naoto1.yoshida@gmail.com)`）を明示的に設定。
- **F-07（新規）** [Inference]: 1回のスキャンで取得する上限件数は 100件（Rate Limiting と兼ね合い）。

### 4.2 正規化（共通スキーマ）
- **F-10** [Inference]: 取得案件を以下のスキーマに正規化する。

```yaml
job_id: string            # CW案件ID（URL末尾から抽出）
title: string             # タイトル
description: text         # 案件本文
category: string          # カテゴリ
tags: list[string]        # タグ
budget_text: string|null  # 予算表記（HTMLから抽出した生テキスト、正規化は Phase 1.5）
url: string               # 案件URL（絶対URL）
posted_at: datetime|null  # 掲載日時（HTML から抽出可能な範囲）
raw_text: text            # 案件本文全体（応募文生成スキルへの入力）
scanned_at: datetime      # スキャン日時
```

[Unknown] `client_rating` / `applicants_count` は公開ページからの抽出可否が未確定。抽出可能な場合は追加、不可能な場合は Phase 1.5（ログイン後エンリッチ）で扱う。

### 4.3 スコアリング（Claude Haiku 4.5）
- **F-20** [Inference]: §5 のスコアリング基準に従い、各案件に 0〜100 点のスコアを付与する。
- **F-21** [Fact]: スコアリングモデルは **Claude Haiku 4.5** を採用。Anthropic SDK 経由で構造化 JSON 出力を取得する。
- **F-22** [Inference]: モデルIDは環境変数 `ANTHROPIC_HAIKU_MODEL` で注入し、モデル更新時に `.env` 書換のみで差替可能とする。デフォルトは Anthropic 公式ドキュメントから取得した最新の日付付きIDを `.env.example` に記載。
- **F-23** [Inference]: スコア 60 点以上を「応募候補」、59 以下は非候補として `daily_candidates` タブには書き込まない（`master_jobs_raw` には全件保存）。

### 4.4 応募文生成（Claude Sonnet 4.6 + 既存スキル注入）
- **F-30** [Inference]: §4.3 で「応募候補」となった案件に対し、応募文生成を実行する。
- **F-31** [Fact]: 応募文生成モデルは **Claude Sonnet 4.6** を採用。環境変数 `ANTHROPIC_SONNET_MODEL` で差替可能。
- **F-32** [Fact: SKILL.md 改変禁止方針]: 既存 `crowdworks-proposal-writer` の `SKILL.md` をファイル読込し、そのまま system prompt に丸ごと注入する。SKILL.md 本体は一切改変しない。
- **F-33** [Fact: SKILL.md より]: SKILL.md の絶対ルール10項目（嘘禁止・名前「吉田」固定・LLM最新版・稼働週20-30時間 等）は注入により機械的に遵守される。
- **F-34** [Inference]: トーン（丁寧・フランク・提案型）はスコアリング時に Haiku が合わせて推定・出力し、`daily_candidates` の `tone` 列に格納。オーナーは Sheets 上で上書き可能とする。

### 4.5 蓄積（Google Sheets 直接書き込み）
- **F-40** [Inference]: 生成した応募文を Google Sheets の `daily_candidates` タブに 1行1案件で書き込む。
- **F-41**（改訂）[Inference]: `daily_candidates` タブの列構成:

| 列 | 型 | 説明 |
|---|---|---|
| date | date | 書き込み日（JST） |
| job_id | string | CW案件ID |
| score | int | スコア（0-100） |
| title | string | 案件タイトル |
| url | string | 案件URL（クリックで CW サイトへ遷移） |
| tone | string | 推定トーン（丁寧 / フランク / 提案型） |
| reason | string | Haiku が出力したスコア根拠（1〜2行） |
| proposal_text | text | Sonnet が生成した応募文全文（コピペ対象） |
| status | enum | `PENDING` / `APPLIED` / `SKIPPED` |
| applied_at | datetime | オーナーが APPLIED に更新した時刻（手動入力 or 数式で自動） |

- **F-42**（改訂）[Inference]: `status` 初期値は `PENDING`。オーナーは応募後に手動で `APPLIED` に更新、対象外と判断した案件は `SKIPPED` に更新する。
- **F-43**（改訂）[Inference]: `sent_log` タブと `draft_proposals` タブは v0.2 で廃止。`daily_candidates` に統合。
- **F-44** [Inference]: 同一 `job_id` の再書き込み防止: `master_jobs_raw` 側の job_id を前日以前と比較し、新着案件のみ `daily_candidates` に書き込む（冪等性担保）。

### 4.6 スケジューリング（GitHub Actions cron）
- **F-80**（改訂）[Inference]: 実行基盤は **GitHub Actions cron に確定**（v0.1 の GAS トリガー選択肢は削除）。
- **F-81** [Fact]: GitHub Actions の scheduled workflow は `:00` ピッタリで混雑・遅延しやすいため、cron は JST 9 時台の `:00` を避けた時刻に設定する（例: `22 0 * * *` UTC = 09:22 JST）。
- **F-82** [Inference]: 実行ワークフロー目安（所要時間は案件数に依存）:
  - 起動 → robots.txt 取得・User-Agent 設定
  - 案件一覧ページ取得（Rate Limit 1 秒/req）
  - 詳細ページ巡回で `raw_text` 取得
  - Haiku でスコアリング
  - 60点以上を Sonnet で応募文生成
  - Sheets `daily_candidates` タブ書き込み
  - `execution_log` タブへ実行サマリ記録

### 4.7 日次上限（規約遵守のハードガード）
- **F-74**（改訂）[Inference]: 1日あたり `daily_candidates` に書き込む案件は **上限 10 件**。超過分は翌日スキャンで再評価（v0.1 の 10件記述を v0.3 正式仕様として確定。Jobs 決定 5件 から緩和）。
- **F-75**（新規）[Inference]: 同一 `job_id` の二重書き込み防止は `master_jobs_raw` の `job_id` を冪等性キーとして参照する。

### 4.8 ログ・監査証跡
- **F-90** [Inference]: 全実行ログ（スキャン件数、スコア分布、生成件数、エラー）を `execution_log` タブに記録する。
- **F-91**（改訂）[Inference]: オーナーの `status` 更新は Sheets の編集履歴で追跡可能とする（別途ログ不要）。
- **F-92** [Inference]: ログ保持期間は 180 日（初期値）、以降は月次で集計シートへ圧縮。

### 4.9 廃止した要件（v0.1 からの削除一覧）
以下の v0.1 要件は v0.2 で完全削除する:
- F-50 〜 F-52（Gmail 通知メール送信関連）
- F-60 〜 F-62（Sheets `owner_action` 列ベースの承認フロー、Gmail 下書き作成ベースの承認）
- F-70 〜 F-73（CrowdWorks フォームへの自動送信・ブラウザ自動化）
- F-04 相当の RSS 取得・RSS パース関連
- Gemini API 関連の全記述（NFR-31 内訳含む）

---

## 5. スコアリング基準の詳細

### 5.1 スコア構成要素（初期ウェイト案）[Inference]

| 項目 | ウェイト | 算出ルール |
|---|---|---|
| 5.1.1 単価適合度 | 30pt | 固定30万円以上=30、10-30万=20、5-10万=10、時給3000円以上=25、時給1500-3000円=15、時給1500円未満=0（`budget_text` から Haiku が推定） |
| 5.1.2 案件ジャンル適合度 | 35pt | 既存実績10件との一致度。§5.2 のマッピングに従う（v0.1 の 25pt から増加、クライアント評価/応募者数が公開ページから取得不可の可能性があるため） |
| 5.1.3 鮮度 | 15pt | 掲載6時間以内=15、24時間以内=10、3日以内=5、それ以降=0 |
| 5.1.4 案件情報の充実度 | 10pt | 本文200字以上で具体的要件が明示=10、100-200字=5、100字未満=0 |
| 5.1.5 技術スタック明記度 | 10pt | 使用技術が明示されていて吉田の得意領域と合致=10、曖昧=5、不一致=0 |

[Inference] v0.1 の「クライアント評価 20pt」「応募者数 15pt」は公開ページから抽出できるかが [Unknown]。抽出不可の場合は Phase 1.5 でログイン後エンリッチする前提で v0.2 では削除、その分を「ジャンル適合度」に加算。

### 5.2 吉田さん向き案件マッピング [Inference + Fact: SKILL.md より]

| 案件キーワード | 適合度(35pt満点) | 根拠となる実績 |
|---|---|---|
| GAS / Google Apps Script / スプレッドシート自動化 | 35 | 実績1 営業リスト自動作成、実績10 Antigravity |
| RAG / 社内文書検索 / チャットボット | 35 | 実績2 社内文書Q&A |
| Claude API / Anthropic API | 32 | 実績1, 5, 10 |
| 業務効率化 / 営業DX / 製造業DX | 35 | 実績全般＋本業での現場知見 |
| 議事録 / 音声→文字起こし | 30 | 実績5 議事録自動生成 |
| Web検索自動化 / スクレイピング | 28 | 実績7, 10 |
| Gmail API / メール自動化 | 28 | 実績6 |
| Dify | 15（過大評価禁止） | 実績8 のみ。SKILL.md 第8項目遵守 |
| 画像生成 / 動画生成 / 3D | 5 | 実績なし |
| Next.js フルスタック開発 | 15 | 基礎レベルのみ、誇張禁止 |
| iOSネイティブ / Android Kotlin / Unity | 0 | 実績ゼロ、対応不可 |

### 5.3 除外ルール（即 0点 / 候補外）[Inference]
- E-01: 時給1000円未満 かつ 応募者数明示で30人以上 の低単価スパム案件
- E-02: iOS/Androidネイティブ、Unity、ゲーム開発、動画編集、デザイン制作
- E-03: 「継続案件・月固定10時間で月3000円」等の明らかに割に合わない案件
- E-04: 募集本文が100文字未満の情報不足案件（応募文を書けない）
- E-05: CrowdWorks 外でのやり取りを強要する案件（規約違反リスク）

### 5.4 スコアリングの運用改善 [Inference]
- 初期1ヶ月は Phase 1 運用データ（返信率・成約率）を `daily_candidates` の `status` から集計
- 以降、返信率と各項目の相関を分析し、ウェイトを `scoring_config` タブで手動調整
- Phase 1.5 で `scoring_config` の動的読込機能を追加

---

## 6. 非機能要件

### 6.1 CrowdWorks 利用規約遵守（最重要）
- **NFR-01** [Inference]: **規約違反を絶対に発生させない**（第3条に基づく最優先原則）。
- **NFR-02** [Fact]: `https://crowdworks.jp/public/jobs` は公開ページでログイン不要。公式 RSS 撤回後の代替手段として HTML 取得を採用。
- **NFR-03** [Inference]: 送信は**必ず人間が CrowdWorks サイトで手動実施**する。自動送信・ブラウザ自動化による応募フォーム投入は v0.2 スコープ外（Exit Criteria 達成後の Phase 2 で再検討）。
- **NFR-04**（新規）[Inference]: `robots.txt` の Disallow 指示を厳格に遵守。Crawl-delay の指定がある場合は指定値と §4.1 F-05 の 1 秒/req のうち**長い方**を採用。
- **NFR-05**（新規）[Inference]: User-Agent は TEGG Engineering の識別可能な値を設定し、匿名クローラーとしての挙動を回避する。

### 6.2 レート制限
- **NFR-10** [Inference]: スキャン頻度: 1日1〜2回、連続スキャン禁止。
- **NFR-11** [Inference]: リクエスト間隔: 1 秒/req 以上（詳細ページ巡回含む）。
- **NFR-12** [Inference]: 1日あたり `daily_candidates` への書き込み上限 10 件（F-74 と連動）。

### 6.3 セキュリティ
- **NFR-20** [Inference]: **Anthropic API キー 1 本のみ必要**（Gemini API キー要件は v0.2 で削除）。`.env` で管理、`.gitignore` 登録必須。GitHub Actions では Secrets に注入。
- **NFR-21** [Inference]: Google Service Account JSON は `.gitignore` 登録必須。GitHub Actions では Secrets に格納（誤コミット防止）。
- **NFR-22** [Inference]: Service Account の有効化 API は **Google Sheets API のみ**（Gmail API は v0.2 で削除）。
- **NFR-23** [Inference]: Sheets の共有範囲は「オーナーのみ」、外部公開禁止。
- **NFR-24** [Inference]: 応募文生成ログにクライアント企業の機微情報が含まれる場合、180 日で自動削除（Phase 1.5 実装タスクとして明記）。

### 6.4 運用コスト上限（月額）
- **NFR-30**（改訂）[Inference]: **月額 3,100 円目安**（Maestri 再試算対象として明記）。v0.1 の 1,000 円から上方修正。根拠は Anthropic 単一プロバイダ化による Sonnet 4.6 使用量増。
- **NFR-31**（改訂）[Inference]: 内訳見込み（Maestri 確定前）:
  - Claude Haiku 4.5（スコアリング）: 約 400 円/月
  - Claude Sonnet 4.6（応募文生成）: 約 2,700 円/月
  - GitHub Actions: 無料枠内
  - Google Sheets API: 無料枠内
- **NFR-32** [Inference]: 月額 3,100 円を大幅超過（例: 5,000円超）した場合はオーナー承認を得てから実装続行。

### 6.5 可用性・信頼性
- **NFR-40**（改訂）[Inference]: 毎朝のスキャン失敗時は `execution_log` タブに ERROR 記録。Gmail 通知は v0.2 で撤回したため、オーナーは朝の Sheets チェック時に `execution_log` も確認する運用。
- **NFR-41** [Inference]: HTTP 取得失敗は 3 回まで自動リトライ（指数バックオフ）。それでも失敗した場合は `execution_log` に ERROR を記録し当該実行は中断。
- **NFR-42** [Inference]: Sheets 書込失敗等の致命エラー発生時は即時停止。

---

## 7. インターフェース設計

### 7.1 既存 `crowdworks-proposal-writer` との連携 I/F
**入力インターフェース:** [Fact: SKILL.md より]
- SKILL.md ファイル全体を読込み、Sonnet 4.6 の system prompt に丸ごと注入する。
- User prompt には `raw_text` を「【案件情報】\n{raw_text}」の形で渡し、加えて補助情報（推定トーン・予算・ジャンル）を付与する。

```
【案件情報】
{raw_text}

【補助情報（Federighi→スキル）】
推定トーン: {丁寧 / フランク / 提案型}
案件タイプ: {GAS/RAG/業務効率化/ライティング/コンサル/低単価/未経験領域}
予算: {budget_text}
```

**出力インターフェース:**
- 応募文（テキスト、1案件1文字列）を `daily_candidates.proposal_text` 列へ格納。

**非改変保証:**
- 既存 `SKILL.md` は一切改変しない。本 MVP は「読込・注入」する側として振る舞う。[Fact]

### 7.2 承認UI（Google Sheets 単一 UI）
v0.1 で比較した Slack / Notion / Next.js 等の代替案は v0.2 では検討対象外。**Google Sheets 単一 UI** に確定。オーナーの朝のルーチンは:

1. Sheets の `daily_candidates` タブを開く
2. score 降順で並ぶ当日案件を確認
3. 応募したい案件の `url` をクリックして CrowdWorks サイトへ遷移
4. `proposal_text` をコピーして応募フォームに貼付、手動送信
5. Sheets に戻って `status` を APPLIED に更新、`applied_at` に現在時刻を入力
6. 対象外案件は `status` を SKIPPED に更新

### 7.3 データストア構成（Google Sheets 4タブ）[Inference]
| タブ名 | 用途 |
|---|---|
| `master_jobs_raw` | スキャン生データ（冪等性キー: job_id、全件保存） |
| `daily_candidates` | 応募候補（60点以上、上限10件/日）。オーナーの唯一の作業画面 |
| `execution_log` | スキャン・スコアリング・生成・書き込みの実行ログ |
| `scoring_config` | Phase 1.5 予約（v0.2 では空タブのみ作成） |

v0.1 の `draft_proposals` と `sent_log` は `daily_candidates` に統合済み。

---

## 8. Exit Criteria（Phase1 半自動 → Phase2 完全自動 への移行条件）

[Inference] 以下 5 条件を全て満たすまで Phase 2 への移行検討を開始しない。

- **EC-01**: オーナー応募採用率 70% 以上（`daily_candidates` に書き込まれた案件のうち `status=APPLIED` になった比率、直近連続30件）
- **EC-02**: 応募→返信率 15% 以上（月次計測、連続2ヶ月維持）
- **EC-03**: CrowdWorks アカウントへの規約違反警告・制限・BAN が連続90日間ゼロ
- **EC-04**: スコアリング誤判定（明らかに対応不可な案件が候補化）が月5件未満
- **EC-05**: オーナー主観満足度 4以上/5（月次アンケート、連続3ヶ月）

全条件達成時点で Rubinstein 監査を経て Phase 2 PRD を別途起案する。なお Phase 2 の完全自動送信は CrowdWorks 利用規約の解釈次第であり、規約改定の可能性次第で永続的に Phase 1 運用を継続する判断も有り得る。

---

## 9. リスクと緩和策

| # | リスク | 発生可能性 | 影響度 | 緩和策 |
|---|---|---|---|---|
| R-01 | HTML 構造変更でスクレイピングが破綻 | 中 | 中 | パース失敗を `execution_log` に ERROR 記録、翌朝オーナーが検知 → Woz が即修正 |
| R-02 | LLM による虚偽応募文生成 | 中 | 高 | SKILL.md 絶対ルール10項目が対策済。`reason` 列で Haiku のスコア根拠を確認可能 |
| R-03 | スコアリング誤判定で低品質案件が候補化 | 中 | 中 | オーナーの最終判断（APPLIED/SKIPPED）で吸収。月次でウェイト調整 |
| R-04 | Anthropic API 料金想定超過 | 低 | 中 | NFR-32 で月額監視。5,000円超過でオーナー承認ゲート |
| R-05 | 応募文の同質化 | 中 | 高 | SKILL.md のトーン3種＋案件タイプ別差別化ロジックで担保 |
| R-06 | オーナー不在時の `daily_candidates` 滞留 | 中 | 低 | 鮮度スコアで自動的に低下、古い案件は翌日候補から除外 |
| R-07 | robots.txt 変更でアクセス不可に | 低 | 高 | 実行前に必ず最新を取得してチェック（NFR-04）、違反検知で即停止 |
| R-08 | Anthropic 側のレート制限 | 低 | 中 | 日次上限10件の設計で確実に枠内。Tier 1 で十分 |

---

## 10. オープンクエスチョン（オーナー/Jobsへの確認待ち項目）

1. **Q-01**: 案件取得対象カテゴリ・タグの最終確定（§4.1 F-02 は仮置き）。オーナーに「応募したいジャンル優先順」のヒアリングが必要。
2. **Q-02**: `client_rating` / `applicants_count` を公開ページから抽出可能か（Woz 調査事項）。不可なら Phase 1.5 へ後送り。
3. **Q-03**: GitHub Actions cron の具体的起動時刻（例: 09:22 JST）の最終確定。
4. **Q-04**: オーナーの朝のルーチン運用（Sheets 確認時刻の目安）と、日次上限10件が実運用で多すぎないか。
5. **Q-05**: Phase 1.5 で `scoring_config` 動的読込を実装するタイミング（Phase 1 稼働 1 ヶ月後を目安とするか）。
6. **Q-06**: Rubinstein 再監査の発動タイミング（PRD v0.2 / feasibility v0.2 / implementation_plan v0.2 の3文書揃い次第）。

---

## 11. 次アクション（参考）

[Inference] 本 PRD v0.2 を Jobs レビュー後、以下を推奨:
1. **Woz**: feasibility v0.2（HTTP取得規約精査、Claude 統一方針、Rate limiting 設計）
2. **Woz**: implementation_plan v0.2（feasibility v0.2 完了後に着手）
3. **Maestri**: NFR-30 月額 3,100 円の再試算精緻化
4. **Rubinstein**: 3 文書揃い次第、再監査発動
5. **オーナー側作業**: Anthropic API キー取得、Google Cloud Service Account 作成（Sheets API のみ有効化）、Google Sheets 新規作成＋4タブ初期化

---

**最終更新**: 2026-04-24 / **改訂者**: Federighi (Head of Product) / **バージョン**: v0.2 / **前版**: v0.1 (2026-04-21)
