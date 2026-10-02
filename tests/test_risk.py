from decision.demo import billing_case
from decision.loop import prepare


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
