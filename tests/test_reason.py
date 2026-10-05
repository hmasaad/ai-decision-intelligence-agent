from decision.agent import DecisionAgent
from decision.demo import billing_case
from decision.graph import ask
from decision.loop import prepare
from decision.reason import render_map

FLUTTER = "Should we migrate our Flutter app to architecture X?"


def test_the_map_connects_evidence_to_the_billing_recommendation():
    text = render_map(prepare(billing_case()))
    assert "Evidence" in text
    assert "──────────────┐" in text
    assert "Assumption" in text
    assert "Constraint → Option" in text
    assert "Outcome" in text
    assert "Decision" in text
    assert "Architecture review, 58%." in text
    assert "at 70% confidence." in text
    assert "Confidence 58%." in text
    assert "Confidence 70%" not in text
    assert "Staffing plan, 80%." in text
    assert "No evidence is on record." in text
    assert "SRE (opinion), 76%." in text
    assert "Admits Partial migration. Blocks Full migration." in text
    assert "B. Partial migration" in text
    assert "$74,400 benefit" in text
    assert "Recommends B. Partial migration." in text
    assert "Full migration scores higher and is blocked by 3 engineers available, the 8-week timeline, and no production downtime." in text


def test_why_walks_the_path_to_partial_migration():
    case = prepare(billing_case())
    answer = ask([case], "Why did you reach this recommendation?")
    assert answer.startswith("Why did you reach this recommendation?")
    assert "B. Partial migration is the recommendation because this path reaches it." in answer
    assert "Constraint → Option" in answer
    assert "Its expected outcome is $74,400 benefit." in answer


def test_an_unscored_decision_has_no_path_to_explain(tmp_path):
    agent = DecisionAgent(tmp_path)
    case = agent.register(FLUTTER)
    text = render_map(case)
    assert text.startswith("Nothing is recommended yet")
    assert "Stay on the current architecture" not in text
    recorded = agent.update(case.id, options=["Stay on the current architecture", "Migrate to architecture X"])
    traced = render_map(recorded)
    assert traced.startswith("Nothing is recommended yet")
    assert "A. Stay on the current architecture" not in traced
