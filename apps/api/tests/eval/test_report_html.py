"""The HTML report viewer must be honest, self-contained, and injection-safe."""

from __future__ import annotations

from evalkit.report_html import render_html, save_html
from evalkit.types import CaseResult, CheckResult, Report


def _report() -> Report:
    return Report(
        schema_version="1.0",
        run_meta={
            "suite": "smoke",
            "summary": {
                "total_cases": 3,
                "total_passed": 2,
                "overall_pass_rate": 2 / 3,
                "capabilities_below_threshold": ["budget"],
            },
        },
        per_case=[
            CaseResult(
                golden_id="routing-happy-en-01",
                capability="routing",
                scenario="happy",
                suite="smoke",
                checks=[CheckResult(name="flow_match", passed=True, detail="ok")],
                passed=True,
            ),
            CaseResult(
                golden_id="routing-happy-en-02",
                capability="routing",
                scenario="happy",
                suite="smoke",
                checks=[CheckResult(name="flow_match", passed=True)],
                passed=True,
            ),
            CaseResult(
                golden_id="budget-happy-en-01",
                capability="budget",
                scenario="happy",
                suite="smoke",
                checks=[
                    CheckResult(
                        name="flow_match",
                        passed=False,
                        score=0.0,
                        detail="expected='budget' got='journal'",
                    )
                ],
                passed=False,
            ),
        ],
        per_capability={
            "routing": {
                "passed": 2,
                "total": 2,
                "pass_rate": 1.0,
                "threshold": 0.7,
                "meets_threshold": True,
            },
            "budget": {
                "passed": 0,
                "total": 1,
                "pass_rate": 0.0,
                "threshold": 0.7,
                "meets_threshold": False,
            },
        },
    )


def test_render_shows_totals_and_percentage():
    html = render_html(_report())

    assert "66.7%" in html  # overall pass rate
    assert ">3<" in html and ">2<" in html and ">1<" in html  # total / passed / failed
    assert "budget" in html and "routing" in html


def test_every_case_is_rendered_with_its_verdict():
    html = render_html(_report())

    for golden_id in (
        "routing-happy-en-01",
        "routing-happy-en-02",
        "budget-happy-en-01",
    ):
        assert golden_id in html
    # The failing case carries its check detail so the page explains WHY it failed.
    assert "expected=&#x27;budget&#x27; got=&#x27;journal&#x27;" in html
    assert html.count('data-passed="false"') == 1
    assert html.count('data-passed="true"') == 2


def test_detail_text_is_escaped_not_injected():
    """A golden's reply/detail is agent-authored text — it must never become markup."""
    report = _report()
    report.per_case[2].checks[0].detail = "<script>alert('xss')</script>"

    html = render_html(report)

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html


def test_page_is_self_contained():
    """No CDN/asset fetches — the page must open straight from disk or a CI artifact."""
    html = render_html(_report())

    assert "<style>" in html and "<script>" in html
    assert "http://" not in html and "https://" not in html
    assert "src=" not in html


def test_save_html_creates_parent_dirs(tmp_path):
    target = tmp_path / "reports" / "nested" / "latest.html"

    save_html(_report(), target)

    assert target.exists()
    assert "Agent eval report" in target.read_text(encoding="utf-8")
