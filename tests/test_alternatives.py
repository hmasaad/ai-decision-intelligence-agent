from decision.agent import DecisionAgent
from decision.alternatives import render_alternatives
from decision.demo import billing_case
from decision.frame import frame_request
from decision.loop import prepare

FLUTTER = "Should we migrate our Flutter app to architecture X?"


def test_every_billing_option_is_graded_on_the_same_criteria():
    text = render_alternatives(prepare(billing_case()))
    assert "Option A: A. Do nothing" in text
    assert "Option B: B. Partial migration" in text
    assert "Option C: C. Full migration" in text
    assert "Status quo: A. Do nothing" in text
    assert "Hybrid: B. Partial migration" in text
    assert "Also on the table: D. Managed billing service" in text
    assert "A. Do nothing               High    Fast    High  Low" in text
    assert "B. Partial migration        Low     Medium  Low   High" in text
    assert "C. Full migration           Low     Slow    Low   High" in text
    assert "D. Managed billing service  Medium  Slow    Low   Medium" in text
    assert "Hybrid. Recommended. $74,400 benefit." in text
    assert "$103,200 benefit." in text
    assert "Needs 5 engineers and 3 are available." in text
    assert "C. Full migration has the highest expected value, $103,200 benefit." in text
    assert "It is blocked." in text
    assert "The recommendation is B. Partial migration." in text


def test_an_unscored_decision_is_not_given_grades():
    case = prepare(frame_request("Should we raise the price?", objective="Grow revenue."))
    text = render_alternatives(case)
    assert "Status quo: A. Do nothing" in text
    assert "Hybrid: Not on record." in text
    assert "Option C: Not on record." in text
    assert "Not scored yet." in text
    assert "Low" not in text
    assert "Fast" not in text


def test_a_registered_question_does_not_gain_options(tmp_path):
    agent = DecisionAgent(tmp_path)
    case = agent.register(FLUTTER)
    text = agent.alternatives(case.id)
    assert case.options == []
    assert agent.get(case.id).options == []
    assert "No options are on record, so there is nothing to grade." in text
    assert "Do nothing" not in text
    assert "Partial migration" not in text
