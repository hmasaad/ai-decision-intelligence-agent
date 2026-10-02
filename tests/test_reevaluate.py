from datetime import date

import pytest

from decision.demo import billing_case
from decision.errors import DecisionError
from decision.loop import prepare
from decision.models import Evidence
from decision.reevaluate import incorporate, payments_regulation


def test_a_regulation_invalidates_the_downtime_assumption():
    case = prepare(billing_case())
    updated = incorporate(case, payments_regulation())
    review = updated.reevaluations[-1]
    assert review.assumption.startswith(
        "The assumption that production downtime is forbidden is no longer valid."
    )
    assert "no longer blocked by downtime" in review.risk
    assert review.outcome == "The expected outcome is unchanged at $74,400 benefit."
    assert review.confidence_before == "medium"
    assert review.confidence_after == "low"
    assert updated.brief is not None
    assert updated.brief.recommendation_key == "B"
    assert updated.brief.confidence == "low"
    assert updated.status.value == "briefed"
    full = updated.scenario("C", "expected")
    assert full is not None
    assert "downtime" not in full.block_codes
    assert "headcount" in full.block_codes


def test_evidence_that_challenges_nothing_does_not_reopen_the_decision():
    case = prepare(billing_case())
    note = Evidence(
        id="release-share",
        kind="metric",
        statement="Billing is on the critical path of 40% of releases this month.",
        source="Release analytics",
        channel="product_analytics",
        observed_at=date(2026, 10, 1),
        confidence=0.8,
    )
    updated = incorporate(case, note)
    assert updated.reevaluations == []
    assert updated.brief is not None
    assert updated.brief.confidence == "medium"
    assert any(item.id == "release-share" for item in updated.evidence)
    with pytest.raises(DecisionError):
        incorporate(updated, note)
