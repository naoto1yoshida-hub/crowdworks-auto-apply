"""CrowdWorks 自動応募システム v0.3 — 正規化スキーマ定義。

実装計画書 v0.2 §Task 2 / feasibility v0.2 §3.3, §5.3 に対応。

- Job: CrowdWorks 案件の正規化レコード（fetcher / parser → 以降の全フェーズで共有）
- Scored: Scorer（Claude Haiku 4.5）が生成する構造化スコア出力
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    """CrowdWorks 案件の正規化スキーマ（feasibility v0.2 §3.3）.

    Required:
        job_id: CrowdWorks の案件 ID（冪等性キー、master_jobs_raw タブの主キー）
        title: 案件タイトル
        url: 詳細ページ URL
        description: 案件本文（詳細ページ取得結果）
        scanned_at: 当該パイプライン実行が当案件をスキャンした UTC 時刻

    Optional:
        budget_text: 報酬表記（パース未確定のため文字列のまま保持）
        category: CrowdWorks のカテゴリ表記
        posted_at: 案件掲載時刻（タイムゾーン付き）
    """

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
    """Scorer（Claude Haiku 4.5）の構造化出力（feasibility v0.2 §5.3）.

    feasibility v0.2 / implementation_plan v0.2 のスコアリング仕様:
        - total_score: 0-100（lucrative_score + fit_score + 補正、Haiku 出力）
        - lucrative_score: 0-50（収益性）
        - fit_score: 0-50（オーナー強み適合度）
        - tone_hint: 応募文生成時のトーン指示（"提案型" / "共感型" 等）
        - reason: スコアリング根拠（200 字以内、Sheets 表示用）
        - category_detected: Haiku が分類したカテゴリ詳細
    """

    job: Job
    total_score: int
    lucrative_score: int
    fit_score: int
    tone_hint: str
    reason: str
    category_detected: str
