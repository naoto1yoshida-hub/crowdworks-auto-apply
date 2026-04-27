# CrowdWorks 自動応募 Phase 1 監査レポート v0.2

**バージョン**: v0.2
**監査日**: 2026-04-24
**監査者**: Rubinstein (Head of Audit)
**前版**: v0.1 (2026-04-21, CONDITIONAL GO)
**対象文書（今回監査）**:
- `projects/crowdworks_auto_apply/requirements/PRD.md` (Federighi v0.2, 2026-04-24)
- `projects/crowdworks_auto_apply/requirements/feasibility.md` (Woz v0.2, 2026-04-24)
- `projects/crowdworks_auto_apply/requirements/implementation_plan.md` (Woz v0.2, 2026-04-24)

---

## 0. エグゼクティブサマリ（結論ファースト）

**判定**: **CONDITIONAL GO**（Critical 1 件・Major 5 件・Minor 7 件。Critical C-1 を是正すれば実装着手可。v0.1 の Critical 3 件はすべて解消済み）

**根拠 3 点:**

1. [Fact] v0.1 監査で致命とした Critical 3 件（C-1 RSS URL / C-2 Claude モデル ID / C-3 Gemini 廃止 SDK）はいずれも v0.3 設計刷新で構造的に解消された。RSS は撤回・HTTP 取得に一本化、モデル ID は環境変数化、Gemini は Anthropic 単一化で消滅した。[Fact: PRD §22/26/28, feasibility §0, implementation_plan §0]
2. [Fact] しかし `implementation_plan.md:130` で `anthropic==0.40.0` にピン止めされている一方、同一著者の `feasibility.md:569` が「anthropic 2026-04 時点で 0.87+」と [Fact] 表記しており、**同じ Woz 署名の v0.2 文書間で約 40 マイナーバージョンの食い違い**が存在する。これは第2条（ハルシネーション禁止）と第1条（Fact 分類）に抵触し、新規 Critical C-1 として計上する。
3. [Inference] PRD F-41 列構成（10 列、`tone`）と implementation_plan / feasibility の列構成（12 列、`tone_hint`、`category` / `owner_memo` 追加）が v0.1 M-2 と同様の不整合を抱えたまま残存。自動解消したはずの M-2 は Major 級で未解消（再発扱いで M-2' として継続）。加えてコスト試算（PRD NFR-30 の 3,100 円と feasibility §7.1 の 1,418 円計算結果）にも乖離がある。

**NO-GO にしなかった理由:** Critical C-1 は `requirements.txt` のバージョン数値 1 行と関連テスト文字列の置換のみで解消可能な軽微な修正。設計骨格・規約整合・SKILL.md 非改変保全は合格水準。

**GO にしなかった理由:** C-1 を無視して着手すると `pip install` 時点で feasibility の [Fact] 表記と矛盾する古いバージョンが入り、v0.1 C-3（廃止予定 SDK を新規採用）と同型の技術的負債を初日から抱える。第3条（忖度排除）の観点でも、feasibility 自身が「古い」と明示したバージョンを implementation_plan が採用している論理破綻を放置できない。

**定量サマリ:**
- Critical（着手前必修）: **1 件**（v0.1: 3 件 → v0.2: 1 件新規発生）
- Major（着手後速やかに）: **5 件**（v0.1: 7 件 → v0.2: 2 件継続 + 3 件新規）
- Minor（改善推奨）: **7 件**（v0.1: 6 件 → v0.2: 3 件継続 + 4 件新規）

---

## 1. 監査観点別サマリ

| # | 観点 | 評価 | 主な発見 |
|---|---|---|---|
| 1 | 第1条 情報の3層分類 | ○ | PRD/feasibility は [Fact]/[Inference]/[Unknown] を丁寧に付与。implementation_plan は冒頭 §0 のみラベル明示、本文は [Inference] が間接記述。[Fact] と宣言した `anthropic` バージョンが他文書 [Fact] と矛盾する事例あり（C-1）|
| 2 | 第2条 ハルシネーション | △ | `anthropic==0.40.0` が feasibility 自身の「最新系列 0.87+」Fact と齟齬（C-1）。Claude モデル ID `claude-haiku-4-5-20251001` / `claude-sonnet-4-6` は feasibility で WebFetch [Fact] 根拠を明示、本監査環境では再検証不可だが形式合理・第5条の対処（環境変数化）で運用リスクは緩和 |
| 3 | 3文書相互整合 | △ | F-07 100件上限 vs `MAX_DETAIL_FETCH=30` の PRD/実装乖離（m-1'）、F-41 列構成不整合（M-2'）、User-Agent 文字列不一致（M-3'）、トーン値「丁寧」vs「丁寧硬め」（m-2'）、コスト試算 3,100 vs 1,418 乖離（M-4'）、カテゴリ絞り込み方針の PRD/feasibility 乖離（m-3'）|
| 4 | v0.1 指摘処理 | ○ | Critical 3 件は全消滅を確認。C-2 環境変数化は §5.2 で具体実装あり。M-2 は未解消（M-2' として継続）、M-4/M-5/M-6/M-7 はいずれも対応確認済 |
| 5 | 新規リスク緩和 | ○ | Bot 検知 R3・HTML 構造変化 R1・規約改定 R7 は feasibility §8 に明示、implementation_plan Task 4 で `BlockedError` 即停止・セレクタ環境変数化・robots.txt 実行時アサートとして実装タスク化済 |
| 6 | writing-plans 準拠 | ◎ | Goal/Architecture/Tech Stack ヘッダ、File Structure、2-5 分粒度、RED→GREEN、完全コード、Self-Review、verification-before-completion の証拠要求まで完備 |
| 7 | SKILL.md 不可侵 | ◎ | Task 8 で `load_skill_markdown` が `Path.read_text` のみ、書換 API なし。system prompt に丸ごと注入、引数順・型・テスト全てで「改変なし」を明文化 |
| 8 | 第7条 絵文字禁止 | ◎ | 3 文書いずれにも絵文字検出ゼロ（正規表現スキャン実施、2026-04-24）|

---

## 2. 指摘一覧

### 2.1 Critical Findings（着手前必修）

---

#### C-1. `anthropic==0.40.0` ピン止めが feasibility 自身の [Fact] 「0.87+」と矛盾

**対象文書:** implementation_plan.md（Woz）

**該当箇所と引用:**
- `implementation_plan.md:18` 「`anthropic==0.40.0`（Claude API、Haiku 4.5 スコアリング + Sonnet 4.6 SKILL.md 注入）[Inference: v0.1 指定 0.39.0 より新しい安定系列]」
- `implementation_plan.md:130` `requirements.txt` 内の `anthropic==0.40.0`
- `implementation_plan.md:140` 「[Inference] `anthropic==0.40.0` は着手時点で `pip index versions anthropic` により当時の最新安定版を再確認し、必要なら日付付近の最新版にアップデートしてピン止めすること」
- `feasibility.md:569` 「LLM SDK | anthropic | 最新（Python ≥3.9） | [Fact] PyPI `anthropic` 最新系列、2026-04 時点で 0.87+」

**問題:**
1. **[Fact]** 同じ v0.2 世代で同じ Woz 署名の feasibility が `[Fact] PyPI 2026-04 時点で 0.87+` と宣言しているのに、implementation_plan は約 40 マイナーバージョン古い `0.40.0` を [Inference] でピン止めしている。第1条（Fact/Inference 分類の混同厳禁）および第2条（ハルシネーション禁止）に抵触。
2. **[Inference]** `0.40.0` 前後には Anthropic SDK の `messages.create` 周辺の重要な API 変更（tool_use、prompt caching、`response_format` 類）が複数含まれている可能性が高い。feasibility §5.3 / §5.5 が前提とするプロンプトキャッシング・構造化出力機能が 0.40.0 で動作しない場合、Task 6（Scorer）/ Task 8（ProposalGen）が本番初回実行で AttributeError 等で破綻する可能性がある。
3. **[Fact]** v0.1 audit の C-3（google-generativeai 廃止予定 SDK を新規採用）と**完全に同じパターン**（feasibility/実態より 1 年以上古い SDK を新規採用）。v0.1 audit で Woz が学習したはずの同型ハルシネーションが再発している。

**影響:**
- `pip install -r requirements.txt` 時点で SDK バージョンは確定する。Task 6/8 の GREEN テストは MagicMock で通るが、Task 12 の実運用 smoke test で実 API 呼び出しが API 互換破壊により失敗する蓋然性が高い。
- feasibility §7.2 のプロンプトキャッシング評価は 0.40.0 で実装可能か [Unknown]（少なくとも 0.40.0 は 2024 年前半系列で、cache_control 機能が正式サポートされていない可能性）。

**推奨修正:**
1. [Fact] `implementation_plan.md:18 / :130` の `anthropic==0.40.0` を **feasibility §11 の「0.87+」と整合する安定版**（例: `anthropic>=0.87,<1.0` ないし Woz が `pip index versions anthropic` で確認した 2026-04-24 時点最新）に差し替える。
2. [Fact] Task 1 Step 6 の `python -c "import ... anthropic"` の直後に `print(anthropic.__version__)` を追加し、期待バージョン以上であることをローカルで目視確認する手順を入れる。
3. [Inference] Task 6 / Task 8 のテストで `anthropic` ライブラリの API 形状依存（`response.content[0].text` など）が SDK 新系列でも有効であることを確認する。

**優先度:** Critical（実装着手前に必ず修正）

---

### 2.2 Major Findings（着手後速やかに）

---

#### M-1'. NFR-30 月額 3,100 円とfeasibility §7.1 小計 1,418 円の数値乖離の根拠が薄弱（新規）

**対象文書:** PRD.md（Federighi）、feasibility.md（Woz）

**該当箇所:**
- `PRD.md:266` 「NFR-30 月額 3,100 円目安」
- `feasibility.md:491` 合計試算「$9.45 ≒ 約 1,418 円」
- `feasibility.md:493-494` 「[Inference] 目安 3,100 円前後への調整: ... 日次50件取得・15件生成 + プロンプトキャッシング未適用相当のより保守側シナリオ」

**問題:**
1. [Fact] feasibility §7.1 の計算は「日次 30 件取得・10 件生成」で 1,418 円/月。
2. [Fact] PRD F-74「日次上限 10 件」は**ハードリミット**（implementation_plan Task 7 の `daily_limit=10` で実装）。15 件/日で試算する根拠が PRD F-74 と論理的に矛盾。
3. [Inference] PRD NFR-30 の 3,100 円は current_focus.md §2.2「コスト試算 [Inference] 合計: 約3,100円/月」に由来するが、current_focus の試算根拠（Haiku 400 円 + Sonnet 2,700 円）は feasibility §7.1 の計算式と整合しない（Sonnet 側 10件/日 × 30日 = 300件で $7.65 ≒ 1,148 円なのに、current_focus の 2,700 円は約 2.4 倍）。

**影響:**
- Maestri 再試算時にどちらの数値を正とするか判断不能。
- 運用開始後、実測が 1,500 円前後に収まった場合に NFR-32「月額 3,100 円を大幅超過（例: 5,000 円超）した場合はオーナー承認」の発火基準が**実態より約2倍高い位置に固定**されてしまい、コスト急上昇を検知するガードとしての実効性が失われる。

**推奨修正:**
1. [Fact] feasibility §7.1 の 10 件/日前提で計算した 1,418 円を基準値として PRD NFR-30 / NFR-32 を再記述する（例: NFR-30「月額 1,500 円目安、3,000 円超でオーナー承認」）。
2. [Inference] もしくは feasibility §7.1 を「日次 10 件（ハードリミット準拠）」に再計算し直し、3,100 円の内訳根拠を明示する。
3. Maestri（CFO）に再試算を正式依頼し、どちらのシナリオを NFR-30 とするか Jobs が最終決定する（第12条 AskUserQuestion 案件）。

**優先度:** Major

---

#### M-2'. PRD F-41 列構成（10列）と implementation_plan / feasibility（12列）の不整合（v0.1 M-2 継続）

**対象文書:** PRD.md、feasibility.md、implementation_plan.md

**該当箇所:**
- `PRD.md:152-163` F-41 列構成: `date | job_id | score | title | url | tone | reason | proposal_text | status | applied_at` （**10 列**、`tone` 列名）
- `feasibility.md:419` daily_candidates 列: `date | job_id | score | title | url | category | tone_hint | reason | proposal_text | status | applied_at | owner_memo` （**12 列**、`tone_hint` 列名、`category` / `owner_memo` 追加）
- `implementation_plan.md:1746` 同上 12 列
- `implementation_plan.md:1861-1874` `append_daily_candidate` 実装が 12 要素配列を append

**問題:**
1. [Fact] PRD F-41 と feasibility §6.3 / implementation_plan Task 9 で**列数（10 vs 12）と列名（tone vs tone_hint）が一致しない**。v0.1 M-2（Sheets 列スキーマ不整合）が根本解消されず、「PRD v0.2 で新スキーマ統一」（current_focus §2.4）が未完遂。
2. [Inference] PRD v0.2 改訂宣言（§22 「5タブ→4タブ集約（Rubinstein M-2 解消）」）が、実際には**タブ数だけ修正して列構成の不整合は残したまま**。README で PRD を読んだオーナーが「tone / reason / proposal_text / status / applied_at」だけで Sheets を作ると、implementation_plan の append が 12 列に対して 10 列しかないシートに書き込むため、`gspread` が暗黙に列追加するか、または列ずれを起こす。

**影響:**
- セットアップ時点でオーナーが Sheets を作る際、どちらの定義に従うか不明確。
- implementation_plan Task 9 テスト（`len(row) == 12`）はシート側 10 列でもモックでは通るため、テスト層で検知できない。

**推奨修正:**
1. **正本を implementation_plan の 12 列に統一**する（category と owner_memo は実運用上有用）。PRD F-41 を 12 列に書き換え、`tone` → `tone_hint` にリネーム。
2. Federighi に PRD v0.3 差分として F-41 表を implementation_plan と一致させるよう差し戻し。
3. 併せて PRD §7.2 Step 5 「status を APPLIED に更新、`applied_at` に現在時刻を入力」の記述は維持可だが、`owner_memo` の存在を §7.2 に追記。

**優先度:** Major

---

#### M-3'. User-Agent 文字列が PRD と feasibility/implementation_plan で不一致（新規）

**対象文書:** PRD.md、feasibility.md、implementation_plan.md

**該当箇所:**
- `PRD.md:114` F-06「User-Agent は TEGG Engineering の識別可能な値（例: `TEGG-Engineering-JobScanner/1.0 (contact: naoto1.yoshida@gmail.com)`）」
- `feasibility.md:53 / :115 / :202` 「`TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)`」
- `implementation_plan.md:41 / :163 / :516 / :2357 / :2485` 同上

**問題:**
1. [Fact] PRD は `TEGG-Engineering-JobScanner/1.0 (contact: ...)` を例示、feasibility / implementation_plan は `TEGG-CrowdWorks-JobFetcher/0.2 (+mailto: ...)` を採用。**プロダクト名・バージョン番号・連絡先プレフィックス（contact: vs +mailto:）すべて異なる**。
2. [Inference] PRD 記述が「例」であることから feasibility 側が優先される解釈は成り立つが、第8条（構造化通信プロトコル）に照らし、同一要件の表記揺れは規律違反。

**影響:**
- 第三者（CrowdWorks 運営や Rubinstein 月次監査）が PRD を見て実機トラフィックの User-Agent と突合できない。
- 実装後に PRD を正とするレビュアーは「PRD の UA と違う」と差し戻す可能性。

**推奨修正:**
1. PRD F-06 の User-Agent 例示を feasibility §3.4 の「`TEGG-CrowdWorks-JobFetcher/0.2 (+mailto:naoto1.yoshida@gmail.com)`」に統一する。
2. Federighi に PRD 差分修正を指示。

**優先度:** Major

---

#### M-4'. PRD F-07「100 件/回」と implementation_plan `MAX_DETAIL_FETCH=30` の乖離（新規）

**対象文書:** PRD.md、implementation_plan.md

**該当箇所:**
- `PRD.md:115` F-07「1回のスキャンで取得する上限件数は 100件（Rate Limiting と兼ね合い）」
- `implementation_plan.md:69` Config `MAX_DETAIL_FETCH=30`
- `implementation_plan.md:2555` Self-Review「PRD F-07 1 回あたり 100 件上限 | Task 3 `MAX_DETAIL_FETCH=30`（詳細取得のみ制限、一覧は全件取得）」
- `feasibility.md:201` 「1 回あたり最大 31 リクエスト（一覧1 + 詳細最大30）」

**問題:**
1. [Fact] PRD は「100 件」、feasibility/implementation_plan は「詳細 30 件（+ 一覧 1）」。**数値が 3 倍以上乖離**。
2. [Inference] Woz の Self-Review は「一覧は全件取得、詳細のみ 30 件制限」と解釈しているが、PRD F-07 の「取得する上限件数」の定義は曖昧。一覧だけカウントするのか詳細までカウントするのかが PRD 側で未定義。
3. [Fact] feasibility §3.4「1 回あたり最大 31 リクエスト」が実装設計として妥当（規約遵守・Rate Limiting との整合）だが、PRD F-07 の「100 件」の根拠が本文に記述なし。

**影響:**
- PRD ベースで運用ドキュメントを書くと、最大取得 100 件を謳いながら実装は最大 30 件しか取ってこないという乖離が運用上の期待値ズレを生む。
- 北極星指標「週 10〜20 件応募」の供給源が 30 件/日 × 7 = 210 件/週からに絞られるため、閾値 60 点通過率次第で供給不足になる可能性。

**推奨修正:**
1. PRD F-07 の「100 件」を feasibility §3.4 の「1 回あたり最大 31 リクエスト（一覧 1 + 詳細 30）」に合わせて書き換える。
2. Federighi が PRD 改訂時に F-07 を「一覧ページから取得する候補数は全件、詳細ページ巡回は最大 30 件」と明確化。

**優先度:** Major

---

#### M-5'. PRD F-41 `reason`「1〜2 行」と scorer 実装「最大 400 字」の記述乖離（新規・軽微）

**対象文書:** PRD.md、implementation_plan.md

**該当箇所:**
- `PRD.md:160` F-41「reason | string | Haiku が出力したスコア根拠（1〜2行）」
- `implementation_plan.md:1393` scorer 実装「`reason=str(data.get("reason") or "-")[:400]`」
- `implementation_plan.md:1344` system prompt「`reason`: `<日本語200字以内のスコア根拠>`」

**問題:**
1. [Fact] PRD は「1〜2 行」、scorer の system prompt は「200 字以内」、実装は「400 字に切り詰め」。3 箇所それぞれ異なる基準。
2. [Inference] 1〜2 行 ≒ 60-120 字、200 字、400 字 の 3 段階のバッファが存在するが、整合性ある設計なのか偶然なのかが読解不能。

**影響:**
- Haiku が 200 字で返しても Sheets 表示で 2 行超過する場合あり。
- オーナーの朝のレビュー UX に影響（Sheets の列幅調整）。

**推奨修正:**
1. PRD F-41 `reason` の「1〜2 行」を「200 字以内（scorer プロンプト指示値と一致）」に書き換えるか、または scorer の指示を「100 字以内 1-2 行」に絞る。
2. 実装側 `[:400]` は安全マージンとして残してよいが、system prompt との整合を表現。

**優先度:** Major（運用上の UX 問題で実装ブロッカーではないが、v0.1 の「PRD と実装の書きぶり不一致」系の継続）

---

### 2.3 Minor Findings（改善推奨）

---

#### m-1'. 「トーン」値の表記揺れ：PRD「丁寧」vs scorer「丁寧硬め」（新規）

**対象:** PRD.md:159 / :293、feasibility.md:354、implementation_plan.md:1343

PRD F-41 の tone 列値列挙は「丁寧 / フランク / 提案型」、scorer 出力 JSON スキーマは「丁寧硬め | フランク | 提案型」。scorer が「丁寧硬め」を返すと PRD 仕様外の値が Sheets に書かれる。

**修正:** 一方に統一。推奨は scorer 側の「丁寧硬め」を「丁寧」に合わせる（PRD の列挙値が正本）。

---

#### m-2'. PRD §4.1 F-02 のカテゴリ列挙と feasibility §3.1「全カテゴリ新着から抽出」の方針乖離（新規）

**対象:** PRD.md:110、feasibility.md:152

PRD F-02 は「対象カテゴリはシステム開発・ホームページ制作・アプリ・ライティング・データ処理...」と列挙、feasibility は「カテゴリ絞り込みは Phase 1 では不要。全カテゴリ新着から scorer が関連案件のみ抽出」。

**修正:** PRD F-02 を「対象 URL は `/public/jobs?order=new`（全カテゴリ新着）。スコアラー側でジャンル適合度を評価してフィルタ」に書き換え、オープンクエスチョン Q-01 のヒアリング対象から外す（scorer プロンプトの調整で足りる）。

---

#### m-3'. PRD NFR-41「3 回リトライ」と RETRY_MAX_ATTEMPTS=2 の解釈乖離（v0.1 継続気味）

**対象:** PRD.md:276、implementation_plan.md:169 / :2575

PRD「3 回まで自動リトライ」、implementation_plan は `RETRY_MAX_ATTEMPTS=2`（初回 + 再試行 2 回 = 計 3 試行）で辻褄を合わせているが、Self-Review で明記しないと読者誤解が残る。

**修正:** `.env.example` のコメントに「RETRY_MAX_ATTEMPTS=2 means initial request + 2 retries = 3 total attempts (NFR-41 準拠)」と追記。

---

#### m-4'. `daily_candidates` タブ「編集履歴で追跡可能」の根拠薄弱（新規）

**対象:** PRD.md:187 F-91

「オーナーの `status` 更新は Sheets の編集履歴で追跡可能とする（別途ログ不要）」と書かれているが、Google Sheets の編集履歴は**1 セルの直前の値までしか UI から直接は見えず、CSV エクスポート経由でも取得困難**。月次の APPLIED 遷移の集計を取りたい場合、`applied_at` 列（F-41）だけで足りるため、F-91 の「編集履歴」への依存記述は削除か再表現が望ましい。

**修正:** F-91 を「オーナーの `status` 更新時刻は `applied_at` 列に記録。Sheets 編集履歴は補助的な参照としてのみ扱う」に書き換え。

---

#### m-5'. Task 7 除外ルール `\bUnity\b` の日本語境界問題（v0.1 M-6 継続）

**対象:** implementation_plan.md:1508 `re.compile(r"\bUnity\b", re.IGNORECASE)`

`\b` は ASCII 単語境界のため、日本語文中「Unityで」「Unityによる」は `\bUnity\b` で必ずヒットする（意図通り）が、英字連結「CommUnity」「immunity」は `\b` 境界外のためヒットしない（これも意図通り）。test_filter.py のテストケースで「community チャット」は `Unity` を含まないため不ヒット確認しているが、**「unityで連動」のような英日ハイフン境界に注意**。v0.1 M-6 の緩和は概ね OK だが、テストケースに「unitychan」「unityスクリプト」等の境界ケースを 1-2 件追加するとより堅牢。

**修正:** `tests/test_filter.py` に英日境界ケースを 2 件追加（例: `s_boundary = _scored(95, title="unityスクリプト作成")` → 除外されること、`s_safe = _scored(95, title="コミュニティ構築支援 " + "x"*200)` → 通ること）。

---

#### m-6'. requirements.txt 他の固定バージョン（`gspread==6.1.4`, `google-auth==2.35.0`, `pytest==8.3.3` 等）が 2024 年系列（新規）

**対象:** implementation_plan.md:128-135

`anthropic` 以外の依存も 2024-10 前後の古いマイナーバージョン固定。C-1 を修正する際に、同じタイミングで各ライブラリを `pip index versions` で最新安定版に更新してピン止めすることを推奨。

**修正:** Task 1 Step 2 に「着手時点で全依存のマイナーバージョンを `pip index versions <pkg>` で確認し最新安定版にピン止めする」手順を明記。

---

#### m-7'. scoring_config タブ「Phase 1 は空タブで作成のみ」の運用意図が README に記載薄い（v0.1 m-5 継続）

**対象:** README §2 / PRD §7.3 / feasibility §6.5

「空タブを作るだけでよい」ことは README §2 に書かれているが、ヘッダ行（`key | value`）を書くのか完全空白なのかが曖昧。

**修正:** README §2 の scoring_config 作成手順で「1 行目に `key | value` とだけ記入、データ行は空で可」と明記。

---

### 2.4 v0.1 監査指摘の処理結果まとめ（§3 で詳細マトリクス）

- **Critical v0.1 → v0.2:** 3 → 0 継続（全て解消）。新規 1 件（C-1）発生で差引 Critical 計 1 件。
- **Major v0.1 → v0.2:** 7 → 2 継続（M-2 は形状変化して M-2' に、残 1 件は後述）+ 3 新規 = 5 件。
- **Minor v0.1 → v0.2:** 6 → 3 継続 + 4 新規 = 7 件。

---

## 3. v0.1 指摘の処理状況マトリクス

| v0.1 ID | 内容 | v0.2 処理 | 根拠（v0.2 文書該当箇所）|
|---|---|---|---|
| **C-1** RSS URL 不一致 | 解消 | RSS 方式を撤回、HTTP スクレイピング方式に切替 | `PRD.md:27` / `feasibility.md:13` / `implementation_plan.md:32` |
| **C-2** Claude モデル ID 最新版乖離 | 解消 | `ANTHROPIC_HAIKU_MODEL` / `ANTHROPIC_SONNET_MODEL` を環境変数化、デフォルト `claude-haiku-4-5-20251001` / `claude-sonnet-4-6` | `feasibility.md:324-338` / `implementation_plan.md:148-149 / :504-505` |
| **C-3** `google-generativeai 0.8.3` 廃止予定 | 解消 | Gemini 全面撤回、Anthropic 単一化 | `feasibility.md:15` / `implementation_plan.md:33 / :47` |
| **M-1** Gemini 2.5 Flash 単価過小評価 | 解消 | Gemini 撤回により論点消失 | `feasibility.md:549` |
| **M-2** Sheets 列スキーマ不整合 | **未解消**（形状変化で M-2' に） | PRD F-41（10列）と feasibility/plan（12列）の不整合が残存 | `PRD.md:152-163` vs `feasibility.md:419` / `implementation_plan.md:1746` |
| **M-3** Gmail ドメイン委任不可 | 解消 | Gmail API 全面撤回、Sheets 直書きに統一 | `PRD.md:26` / `feasibility.md:14` |
| **M-4** cron `:00` ピッタリ遅延 | 解消 | `22 0 * * *`（09:22 JST）に変更 | `implementation_plan.md:2320` / `feasibility.md:20` |
| **M-5** test_sheets_client モック重複 | 解消 | `from_file` / `from_json` の各テストを分離、単独パッチ | `implementation_plan.md:1898-1916` |
| **M-6** filter.py 部分一致で過剰検知 | 解消 | 正規表現 `\b` + タイトル vs 本文分離 | `implementation_plan.md:1505-1517` |
| **M-7** `.env.example` 秘密鍵扱い記述不足 | 解消 | コメント補強 + README トラブルシュート | `implementation_plan.md:189-192 / :2488` |
| **m-1** 送信方式の表現ブレ「半自動ワンクリック」 | 解消 | 全て「人間が CrowdWorks サイトで手動送信」に統一 | `PRD.md:29 / :69 / :93` |
| **m-2** 日次上限「10件 vs 5件」 | 解消（10件で確定） | Jobs 決定変更を v0.3 正式仕様化 | `PRD.md:31 / :182` / `current_focus.md §2.4` |
| **m-3** F-80 GAS トリガー選択肢残存 | 解消 | GitHub Actions cron に確定 | `PRD.md:32 / :170` |
| **m-4** daily.yml cron コメント文言 | 解消 | コメントを「UTC 00:22 = JST 09:22（avoid :00 congestion）」に明記 | `implementation_plan.md:2321` |
| **m-5** scoring_config 運用注記 | 部分解消 | Phase 1 空タブ作成の記述はあるが、ヘッダ行の有無が不明確 → m-7' として継続 | `implementation_plan.md:2427 (README)` |
| **m-6** `max_tokens=2048` マジックナンバー | 未解消 | `generate_proposal(..., max_tokens: int = 2048)` のまま、env/config 化されていない | `implementation_plan.md:1690` |

**処理結果サマリ:**
- 解消: **13 / 16 件**
- 未解消: **3 件**（M-2 → M-2' 昇格継続、m-5 → m-7' 継続、m-6 は未対応のまま残存）
- v0.2 新規発生: Critical 1 件（C-1）、Major 4 件（M-1' / M-3' / M-4' / M-5'）、Minor 6 件（m-1' / m-2' / m-3' / m-4' / m-5' / m-6'）

---

## 4. 3文書相互整合マトリクス

### 4.1 PRD F-要件 × feasibility × implementation_plan カバレッジ

| PRD 要件 | feasibility 対応 | implementation_plan 対応 | 整合度 |
|---|---|---|---|
| F-01 cron 朝 9 時台 非ピッタリ | §3.1 / §4.1 cron 時刻 09:22 | Task 11 `22 0 * * *` | ◎ |
| F-02 `/public/jobs` 対象 | §3.1 `order=new` | Task 3 `CROWDWORKS_LIST_URL` | ○（カテゴリ方針に PRD/feasibility 乖離あり、m-2'）|
| F-03 1日 1-2 回スキャン | §3.4 | Task 11 cron + workflow_dispatch | ◎ |
| F-04 HTML スクレイピング | §3.2 BS4 | Task 4 Fetcher | ◎ |
| F-05 Rate Limit 1秒/req | §3.4 | Task 4 RateLimitedClient | ◎ |
| F-06 robots.txt + User-Agent | §2.1 / §3.4 | Task 4 assert_robots_allows | ○（UA 文字列が PRD と不一致、M-3'）|
| F-07 1 回 100 件上限 | §3.4 最大 31 req | Task 3 MAX_DETAIL_FETCH=30 | △（**数値乖離 M-4'**）|
| F-10 Job 正規化スキーマ | §3.3 Job データスキーマ | Task 2 Job dataclass | ◎ |
| F-20/21 Haiku 4.5 スコアリング | §5.1 / §5.3 | Task 6 | ◎ |
| F-22 Haiku モデル ID 環境変数化 | §5.2 | Task 3 Config / Task 6 引数 | ◎ |
| F-23 60 点閾値 | §6.5 | Task 7 filter | ◎ |
| F-30/31 Sonnet 4.6 応募文生成 | §5.1 / §5.4 | Task 8 | ◎ |
| F-32 SKILL.md 注入 | §5.4 | Task 8 load_skill_markdown | ◎（SKILL.md 不可侵）|
| F-33 絶対ルール 10 項目保全 | §5.4 遵守事項 | Task 8 read_text のみ | ◎ |
| F-34 tone 推定・格納 | §5.3 tone_hint | Task 9 append_daily_candidate | △（**値の表記揺れ m-1'**）|
| F-40/41 Sheets 4 タブ 列構成 | §6 | Task 9 SheetsClient | △（**列数 10 vs 12 不整合 M-2'**）|
| F-42 status=PENDING 初期値 | §6.3 | Task 9 | ◎ |
| F-43 draft_proposals / sent_log 廃止 | §6.1 | Task 9（4 タブ）| ◎ |
| F-44 冪等性 job_id | §3.3 | Task 5 idempotency | ◎ |
| F-74 10 件上限 | §6.5 | Task 3 DAILY_APPLY_LIMIT=10 / Task 7 | ◎ |
| F-80 GitHub Actions 確定 | §4.1 | Task 11 | ◎ |
| F-81 非ピッタリ cron | §1 / §4.1 | Task 11 | ◎ |
| F-90 execution_log | §6.4 | Task 9/10 | ◎ |
| F-91 編集履歴追跡 | 言及なし | 言及なし | △（**運用根拠薄弱 m-4'**）|
| F-92 ログ保持 180 日 | 言及なし | 言及なし（Phase 1.5 予約） | ○ |

### 4.2 PRD NFR 要件 × カバレッジ

| PRD NFR | feasibility 対応 | implementation_plan 対応 | 整合度 |
|---|---|---|---|
| NFR-01 規約違反ゼロ | §2 全文 | Task 4/10 blocked 即停止 | ◎ |
| NFR-02 公開 HTML 限定 | §2.1 robots.txt | Task 4 | ◎ |
| NFR-03 人間送信 | §1 根拠 2 | Task 8 以降 Sheets 書込のみ | ◎ |
| NFR-04 robots.txt + Crawl-delay | §2.1 | Task 4 assert_robots_allows | ○（Bingbot crawl-delay の採用判断明記を推奨）|
| NFR-05 User-Agent 明示 | §3.4 | Task 3 / Task 4 / Task 11 | ○（PRD 例示と実装で文字列不一致、M-3'）|
| NFR-10 スキャン頻度 | §3.4 | Task 11 cron | ◎ |
| NFR-11 1秒/req | §3.4 | Task 4 RateLimitedClient | ◎ |
| NFR-12 日次 10 件上限 | §6.5 | Task 3/7 | ◎ |
| NFR-20 Anthropic APIキー .env | §5.2 | Task 1 .env.example | ◎ |
| NFR-21 SA JSON .gitignore | §12 | Task 1 .gitignore | ◎ |
| NFR-22 Sheets API のみ | §12 | Task 1 / Task 12 README | ◎ |
| NFR-23 Sheets 共有範囲 | 言及なし | Task 12 README §1.3 | ○ |
| NFR-24 機微情報 180 日削除 | 言及なし（Phase 1.5 予約） | 言及なし（Phase 1.5 予約） | ○（PRD 側で Phase 1.5 明示済）|
| NFR-30 月額 3,100 円 | §7.1 / §7.3 | 言及なし | △（**試算乖離 M-1'**）|
| NFR-31 内訳 Haiku 400 / Sonnet 2700 | §7.1 合計 1,418 円 | 言及なし | △（**M-1' と同根**）|
| NFR-32 5,000 円超で承認 | 言及なし | 言及なし | ○ |
| NFR-40 execution_log ERROR | §3.5 / §8 R1 | Task 10 | ◎ |
| NFR-41 HTTP 3 回リトライ | §3.4 Retry 2 回 | Task 4 RETRY_MAX_ATTEMPTS=2 | ○（解釈ブレ m-3'）|
| NFR-42 致命エラー即停止 | §3.5 | Task 10 | ◎ |

### 4.3 feasibility CONDITIONAL 条件 × implementation_plan カバレッジ

| feasibility 条件 | implementation_plan 対応 | 整合度 |
|---|---|---|
| C1 robots.txt 月次監査 | Task 4 assert_robots_allows + Task 12 README に実機 PNG 推奨 | ◎ |
| C2 HTML 構造フォールバック | Task 4 selector_miss warning + Task 11 SELECTOR_* Secret 差替 | ◎ |
| C3 アクセス頻度上限 | Task 11 cron 1 日 1 回 + workflow_dispatch 制限 | ◎ |
| C4 User-Agent 明示 | Task 3 Config デフォルト / Task 11 | ○（M-3'）|
| C5 Cloudflare 即停止 | Task 4 BlockedError | ◎ |
| C6 Phase 2 再審査 | Task 12 README Exit Criteria | ◎ |

### 4.4 新規リスク緩和の実装カバレッジ（Bot 検知 / HTML 構造変化 / Anthropic 単一依存 / レート制限）

| リスク | 実装タスクでの緩和 | 整合度 |
|---|---|---|
| Bot 検知（Cloudflare / CAPTCHA）R3 | Task 4 `BlockedError` で 403/429/503 即停止、Task 10 execution_log に `blocked` 記録、Task 12 README で「回避策を講じず即停止・オーナーに手動 URL 入力フォールバック提案」 | ◎ |
| HTML 構造変化 R1 | Task 3 セレクタ環境変数化、Task 4 selector_miss warning、Task 11 Secret 経由差替 | ◎ |
| Anthropic 単一依存 / API 障害 R5 | Task 10 で score/generate の try/except + execution_log warning、フェイルセーフはなし（Anthropic 障害時は翌日再実行） | ○（フェイルセーフ不要の判断は妥当。ただし R5 「影響度 低」は過小評価の可能性 — Haiku/Sonnet 同時障害で実行完全停止）|
| レート制限（秒間 req / バックオフ）| Task 3 `REQUEST_INTERVAL_SEC=1.0` / `RETRY_BACKOFF_BASE=2.0` / Task 4 `_wait_interval` 実装 | ◎ |

---

## 5. 最終判定と条件

### 判定: **CONDITIONAL GO**

### CONDITIONAL の解消条件（着手前に必ず満たす）

1. **[Critical C-1 解消]** `implementation_plan.md:130` の `anthropic==0.40.0` を、feasibility §11「2026-04 時点 0.87+」[Fact] と整合する安定版に差し替え。Task 1 Step 6 に `anthropic.__version__` 確認手順を追加。
2. **[Major M-2' 解消]** Federighi が PRD F-41 を 12 列 / `tone_hint` 基準に改訂して feasibility / implementation_plan と一致させる。
3. **[Major M-3' 解消]** PRD F-06 の User-Agent 例示を feasibility / implementation_plan と同一文字列に統一。
4. **[Major M-4' 解消]** PRD F-07 の「100 件」を feasibility §3.4「最大 31 リクエスト」と整合する表現に修正。
5. **[Major M-1' 対処方針確定]** NFR-30 を 1,500 円 or 3,100 円のどちらで確定するか Jobs がオーナーと AskUserQuestion で決裁（第12条）。Maestri 再試算を経て PRD NFR-30 / NFR-32 を更新。

### 着手後速やかに対処（Phase 1 実装と並行可）

6. **[M-5']** PRD F-41 `reason` の文字数指示と scorer プロンプトを整合。
7. **[m-1' / m-2' / m-3' / m-4' / m-5' / m-7']** PRD / README / テストの軽微な表記統一、テストケース追加。
8. **[m-6']** `max_tokens` を config 経由で差替可能化（Task 8 / Task 3 への差分）。

### GO にしなかった理由

- [Fact] C-1 は feasibility 自身の [Fact] 表記と implementation_plan の [Inference] ピン止めが正面から矛盾する典型的な第1条・第2条違反。**Woz 単一著者の v0.2 文書内で自家撞着している**ため、忖度排除の原則（第3条）に基づき差し戻し必須。
- [Inference] v0.1 C-3 の同型ハルシネーション（古い SDK の新規採用）が同じパターンで再発しており、規律面での指摘が必要。

### NO-GO にしなかった理由

- [Fact] Critical C-1 は `requirements.txt` の 1 行書き換えとテスト 1 箇所の確認のみで解消可能。設計骨格・規約整合・SKILL.md 保全は合格水準。
- [Fact] v0.1 の Critical 3 件はすべて構造的解消済み（設計刷新による自動消滅を含む）。
- [Inference] Major 5 件は PRD の記述統一作業が主（Federighi 差分）で、実装タスクそのものは feasibility / implementation_plan の 12 列 / 31 req 基準で一貫しているため、PRD を正として修正すれば設計全体は整合する。

### 次アクション

1. **Jobs**: オーナーに AskUserQuestion で NFR-30 確定値（1,500 円 or 3,100 円）を確認。
2. **Woz**: C-1 解消（`anthropic` バージョン修正 + Task 1 Step 6 追加）を implementation_plan に差分反映。
3. **Federighi**: M-2' / M-3' / M-4' / M-5' 対処として PRD v0.3 を発行（F-41 12 列化 / F-06 UA 統一 / F-07 数値修正 / F-41 reason 文字数整合）。
4. **Maestri**: M-1' に基づき NFR-30 / NFR-31 の再試算。
5. **Rubinstein**: C-1 修正後の再監査（本監査の §2.1 条件のみ追検証、Major 以下は著者修正後の差分確認で足りる）。

---

**最終更新**: 2026-04-24 / **監査者**: Rubinstein (Head of Audit) / **バージョン**: v0.2 / **前版**: v0.1 (2026-04-21, CONDITIONAL GO)
