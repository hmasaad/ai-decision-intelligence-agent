from datetime import date

import pytest

from decision.demo import OBSERVED, billing_case
from decision.errors import DecisionError
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes
from decision.models import Evidence
from decision.reevaluate import accept_revision, incorporate, monitor, payments_regulation


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
    assert review.trigger == (
        "The original decision assumed no production downtime. "
        "Current evidence requires a production window. "
        "Re-evaluation recommended."
    )
    assert review.recommendation == "B. Partial migration. The recommendation stays."
    labels = [item.label for item in monitor(updated)]
    assert labels == [
        "New evidence",
        "New risks",
        "Changed assumptions",
        "Changed constraints",
        "Actual outcomes",
    ]


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


def test_a_capacity_change_uses_the_recorded_headcount():
    case = prepare(billing_case())
    updated = incorporate(
        case,
        Evidence(
            id="capacity-cut",
            kind="constraint",
            statement="Two engineers are available this quarter.",
            source="Staffing plan",
            channel="knowledge_base",
            observed_at=date(2026, 10, 3),
            confidence=0.8,
            challenges="headcount",
            limit=2,
        ),
    )
    review = updated.reevaluations[-1]
    assert review.trigger == (
        "The original decision assumed 3 engineers. "
        "Current capacity is now 2. "
        "Re-evaluation recommended."
    )
    assert "5 engineers" not in review.trigger
    assert updated.brief is not None
    assert updated.brief.recommendation_key == "A"
    assert "moves from B. Partial migration to A. Do nothing." in review.recommendation
    assert updated.status.value == "briefed"


def test_a_material_outcome_asks_a_person_to_accept_the_revision():
    case = prepare(billing_case())
    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00", "Platform")
    for step in list(approved.execution):
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)
    learned, _priors = learn(tracked)
    review = learned.reevaluations[-1]
    assert review.kind == "outcome"
    assert review.trigger == (
        "The original decision expected deployment time of 12 minutes. "
        "The recorded result is 15 minutes. "
        "Re-evaluation recommended."
    )
    assert "B. Partial migration. The recommendation stays." in review.recommendation
    assert "15 minutes, not 12 minutes." in review.recommendation
    assert learned.status.value == "learned"
    assert [step.id for step in learned.execution] == ["facade", "slice", "cutover"]
    accepted = accept_revision(learned, "Use 15 minutes next time.", "Platform")
    assert accepted.execution == learned.execution
    assert accepted.reevaluations[-1].accepted_note == "Use 15 minutes next time."
    assert accepted.brief is not None
    assert accepted.brief.recommendation_key == "B"
