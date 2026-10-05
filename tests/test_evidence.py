from datetime import date

from decision.demo import billing_case
from decision.evidence import balance_lines, confidence_band, coverage, freshness, reliability, render_claims
from decision.loop import prepare
from decision.models import CHANNELS
from decision.reevaluate import incorporate, payments_regulation


def test_freshness_follows_the_age_of_the_claim():
    assert freshness(date(2026, 9, 4), date(2026, 10, 2)) == "fresh"
    assert freshness(date(2026, 8, 12), date(2026, 10, 2)) == "aging"
    assert freshness(date(2025, 1, 1), date(2026, 10, 2)) == "stale"


def test_every_billing_claim_has_provenance_and_a_known_source():
    evidence = billing_case().evidence
    seen = {item.channel for item in evidence}
    assert seen == set(CHANNELS)
    for item in evidence:
        assert item.statement
        assert item.source
        assert item.observed_at
        assert 0 <= item.confidence <= 1
        assert confidence_band(item.confidence) in {"high", "medium", "low"}
    counts = {row["id"]: row["count"] for row in coverage(evidence)}
    assert all(counts[channel] >= 1 for channel in CHANNELS)


def test_billing_claims_separate_opinion_from_evidence():
    case = prepare(billing_case())
    by_id = {item.id: item for item in case.evidence}
    assert reliability(by_id["deploy-now"]) == "measured"
    assert reliability(by_id["cost-now"]) == "measured"
    assert reliability(by_id["partial-estimate"]) == "estimated"
    assert reliability(by_id["shadow-read"]) == "observed"
    assert reliability(by_id["notifications-precedent"]) == "historical"
    assert reliability(by_id["vendor-quotes"]) == "reported"
    assert reliability(by_id["staffing"]) == "recorded"
    assert reliability(by_id["invoice-complaints"]) == "opinion"
    assert reliability(by_id["sre"]) == "opinion"

    lines = balance_lines(case)
    assert lines[0] == "10 claims are evidence. 2 claims are opinion."
    assert "No evidence is filed for or against A. Do nothing." in lines
    assert "3 pieces of evidence support B. Partial migration, while 0 contradict it." in lines
    assert (
        "1 piece of evidence supports C. Full migration, while 2 contradict it. "
        "1 of the contradictions is opinion."
    ) in lines
    assert "1 piece of evidence supports D. Managed billing service, while 0 contradict it." in lines

    text = render_claims(case, date(2026, 10, 2))
    assert "├── Reliability" in text
    assert "│   Measured" in text
    assert "└── Supports / contradicts" in text
    assert "Not filed for or against an option." in text
    assert "Supports B. Partial migration." in text
    assert "Contradicts C. Full migration." in text
    assert "Aging" in text


def test_a_regulation_that_requires_a_window_contradicts_the_no_downtime_option():
    case = incorporate(prepare(billing_case()), payments_regulation())
    lines = balance_lines(case)
    assert "3 pieces of evidence support B. Partial migration, while 1 contradicts it." in lines
    assert any(
        "2 pieces of evidence support C. Full migration, while 2 contradict it." in line for line in lines
    )
    assert "1 piece of evidence supports D. Managed billing service, while 1 contradicts it." in lines
