"""Task 2: models（Job / Scored dataclass）の単体テスト。

実装計画書 v0.2 §Task 2 に対応。feasibility v0.2 §3.3 / §5.3 のスキーマを担保する。
"""

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
    job = Job(
        job_id="1",
        title="t",
        url="u",
        description="d",
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
    assert scored.job.job_id == "1"
