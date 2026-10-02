import pytest

from decision.demo import OBSERVED, billing_case
from decision.errors import DecisionError
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes
from decision.models import Stage


def _ready():
    return prepare(billing_case())


def test_partial_migration_is_the_feasible_winner():
    case = _ready()
    keep = case.scenario("A", "expected")
    partial = case.scenario("B", "expected")
    full = case.scenario("C", "expected")
    assert keep is not None and keep.feasible
    assert partial is not None and partial.feasible
    assert full is not None and not full.feasible
    assert set(full.block_codes) == {"headcount", "timeline", "downtime"}
    assert full.score > partial.score > keep.score
    worst = case.scenario("B", "pessimistic")
    assert worst is not None and not worst.feasible
    assert "timeline" in worst.block_codes
    assert worst.headline == "$39,600 benefit"
    delay = next(risk for risk in case.risks if risk.title == "Migration delay")
    assert delay.detail.startswith("In the worst case, needs")
    assert delay.likelihood == "medium" and delay.impact == "high"
    assert delay.detectability == "high" and delay.residual == "medium"
    assert delay.mitigations
    assert case.brief is not None
    managed = case.scenario("D", "expected")
    assert managed is not None and not managed.feasible
    assert managed.block_codes == ["timeline"]
    assert case.option("A").role == "status_quo"
    assert case.option("B").role == "hybrid"
    assert case.brief.recommendation_key == "B"
    assert case.brief.confidence == "medium"
    assert "DECISION" in case.brief.text
    assert "Human approval required" in case.brief.text
    assert "B. Partial migration" in case.brief.text
    assert "Best:      $91,200 benefit" in case.brief.text
    assert "Can the team allocate 2 additional engineers?" in case.brief.text
    assert "Is the downtime requirement negotiable?" in case.brief.text


def test_approval_gates_execution_and_outcomes():
    case = _ready()
    with pytest.raises(DecisionError):
        record_outcomes(case, OBSERVED)

    rejected = apply_review(case, "rejected", "Not this quarter", "2026-10-02T00:00:00+00:00")
    assert rejected.status is Stage.rejected
    assert rejected.execution == []

    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00")
    assert approved.status is Stage.executing
    assert [step.id for step in approved.execution] == ["facade", "slice", "cutover"]
    with pytest.raises(DecisionError):
        record_outcomes(approved, OBSERVED)

    for step in list(approved.execution):
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)
    assert tracked.status is Stage.tracking
    learned, priors = learn(tracked)
    assert learned.status is Stage.learned
    assert learned.lesson is not None
    assert learned.lesson.bias == "optimistic"
    assert learned.lesson.reevaluate
    assert any("25%" in line for line in learned.lesson.statements)
    assert any("stayed inside the 8-week timeline" in line for line in learned.lesson.statements)
    assert any(prior.metric_id == "deploy_time" for prior in priors)
