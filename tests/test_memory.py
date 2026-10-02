from decision.demo import OBSERVED, billing_case
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes
from decision.memory import recall, remember


def test_memory_reconstructs_why_partial_beat_full():
    case = prepare(billing_case())
    item = remember(case)
    assert "best option that satisfies the constraints" in item.why
    assert any("$18,400" in line for line in item.evidence)
    assert any(line.startswith("Timeline limit") for line in item.assumptions)
    assert any(line.startswith("Labor cost") for line in item.assumptions)
    full = next(line for line in item.rejected if line.startswith("C. Full migration"))
    assert "5 engineers" in full
    assert "downtime" in full.lower()
    assert item.approved.startswith("Not approved yet")
    assert item.learned == "The lesson has not been written."

    answer = recall([case], "Why did we choose partial migration instead of full migration?")
    assert "WHY IT WAS MADE" in answer
    assert "5 engineers" in answer

    missing = recall([case], "Why did we choose PostgreSQL instead of DynamoDB?")
    assert missing.startswith("No stored decision")


def test_a_miss_keeps_its_variance_cause_and_learning():
    case = prepare(billing_case())
    approved = apply_review(
        case,
        "approved",
        "Ship the invoice slice",
        "2026-10-02T00:00:00+00:00",
        "Platform",
    )
    for step in approved.execution:
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)

    deploy = next(item for item in tracked.outcomes if item.metric_id == "deploy_time")
    assert deploy.variance == "+25%"
    assert "9–18 minute" in deploy.cause
    assert "Architecture review" in deploy.cause
    assert "58%" in deploy.cause
    assert deploy.learning == (
        "Future estimates of deployment time should start from 15 minutes, not 12 minutes."
    )

    effort = next(item for item in tracked.outcomes if item.metric_id == "effort")
    assert effort.variance == "+17%"
    assert "Platform retrospective" in effort.cause

    learned, _priors = learn(tracked)
    memory = remember(learned)
    assert "Approved by Platform on 2026-10-02." in memory.approved
    assert any("variance +25%" in line for line in memory.afterward)
    assert "25%" in memory.learned
