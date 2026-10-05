import pytest

from decision.approval import render_gate
from decision.demo import OBSERVED, billing_case
from decision.outcomes import render_scorecard
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
    assert "Confidence is medium, 58%." in case.brief.text
    assert "34% lower" in case.brief.text
    assert "$74,400 benefit" in case.brief.text
    assert "Engineering capacity. Full migration needs 5 engineers and 3 are available." in case.brief.text
    assert "The recommendation moves to C. Full migration." in case.brief.text
    assert "The recommendation moves to D. Managed billing service." in case.brief.text
    assert "Put a strangler facade in front of the service." in case.brief.text
    assert case.brief.change_conditions[0] == "Can the team allocate 2 additional engineers?"
    assert "Is the downtime requirement negotiable?" in case.brief.change_conditions


def test_approval_gates_execution_and_outcomes():
    case = _ready()
    with pytest.raises(DecisionError):
        record_outcomes(case, OBSERVED)

    rejected = apply_review(case, "rejected", "Not this quarter", "2026-10-02T00:00:00+00:00")
    assert rejected.status is Stage.rejected
    assert rejected.execution == []

    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00")
    assert approved.status is Stage.executing
    assert approved.human_choice == "B"
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


def test_modify_records_the_persons_choice_and_leaves_the_recommendation():
    case = _ready()
    with pytest.raises(DecisionError, match="Record the reasoning"):
        apply_review(case, "modified", "", "2026-10-02T00:00:00+00:00", "Platform", option_key="C")
    with pytest.raises(DecisionError, match="That is the recommendation"):
        apply_review(
            case,
            "modified",
            "Take the same option.",
            "2026-10-02T00:00:00+00:00",
            "Platform",
            option_key="B",
        )
    modified = apply_review(
        case,
        "modified",
        "The downtime window is open this quarter.",
        "2026-10-02T00:00:00+00:00",
        "Platform",
        option_key="C",
    )
    assert modified.brief is not None
    assert modified.brief.recommendation_key == "B"
    assert modified.human_choice == "C"
    assert modified.review_note == "The downtime window is open this quarter."
    assert modified.status is Stage.executing
    assert [step.id for step in modified.execution] == ["staff", "window", "extract"]
    text = render_gate(modified)
    assert "Agent analyzes" in text
    assert "Agent recommends" in text
    assert "B. Partial migration." in text
    assert "Human reviews" in text
    assert "Approve / Reject / Modify" in text
    assert "Modified. C. Full migration." in text
    assert "The agent recommended B. Partial migration." in text
    assert "Reasoning: The downtime window is open this quarter." in text
    assert "Needs 5 engineers and 3 are available." in text
    assert "The plan follows the option the person chose." in text
    assert "clearly the best" not in text


def test_the_outcome_compares_cost_timeline_and_return_with_what_happened():
    case = _ready()
    before = render_scorecard(case)
    assert "Cost      $12,200 per month" in before
    assert "Timeline  6 weeks" in before
    assert "ROI       $74,400 benefit" in before
    assert "Not recorded." in before
    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00")
    for step in list(approved.execution):
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)
    text = render_scorecard(tracked)
    assert "Cost      $12,800 per month" in text
    assert "Timeline  7 weeks" in text
    assert "ROI       $67,200 benefit" in text
    assert "Variance\n+5%" in text
    assert "Variance\n+17%" in text
    assert "Variance\n-10%" in text
    assert "Why?" in text
    assert "Architecture review" in text
    assert "Platform retrospective" in text
    assert "Inferred from the infrastructure bill." in text
    assert "The return moved from $74,400 benefit to $67,200 benefit." in text
    assert "$100,000" not in text
    assert "$180,000" not in text
