from decision.agent import DecisionAgent
from decision.confidence import render_confidence
from decision.demo import billing_case
from decision.loop import prepare

FLUTTER = "Should we migrate our Flutter app to architecture X?"


def test_regression_has_a_mitigation_and_a_residual():
    case = prepare(billing_case())
    risk = next(item for item in case.risks if item.title == "Migration causes production regression")
    assert risk.likelihood == "medium"
    assert risk.impact == "high"
    assert risk.detectability == "high"
    assert risk.residual == "low/medium"
    assert "Staged rollout of one slice" in risk.mitigations
    assert "Roll back if the error rate exceeds 0.5%" in risk.mitigations

    names = [item.title for item in case.risks]
    assert names == [
        "Migration causes production regression",
        "Migration delay",
        "Engineering capacity",
    ]


def test_the_recommendation_carries_a_percent_and_the_recorded_risks():
    case = prepare(billing_case())
    text = render_confidence(case)
    assert "Recommendation" in text
    assert "B. Partial migration" in text
    assert "Confidence" in text
    assert "58%" in text
    assert "76%" not in text
    assert "clearly the best" not in text
    assert "1. Migration causes production regression" in text
    assert "2. Migration delay" in text
    assert "3. Engineering capacity" in text
    assert "Confidence is 58%, below 60%." in text
    assert "The timeline moves off the recorded 8 weeks. At 9 weeks, confidence is 49%." in text
    assert (
        "Engineering capacity drops below 3 engineers. At 2 engineers, the timeline derives to 12 weeks, "
        "and confidence is 51%. The recommendation moves to D. Managed billing service."
    ) in text
    assert "Confidence is medium, 58%." in case.brief.text


def test_an_unscored_decision_has_no_confidence_percent(tmp_path):
    agent = DecisionAgent(tmp_path)
    text = agent.confidence(agent.register(FLUTTER).id)
    assert "Not recommended yet." in text
    assert "Not scored yet." in text
    assert "58%" not in text
    assert "clearly the best" not in text
