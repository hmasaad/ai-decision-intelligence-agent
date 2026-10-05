from decision.agent import DecisionAgent
from decision.demo import billing_case
from decision.graph import ask
from decision.loop import prepare
from decision.scenarios import render_engine
from decision.simulate import STRESS_CASES

FLUTTER = "Should we migrate our Flutter app to architecture X?"


def test_partial_migration_is_a_benefit_until_it_is_stressed():
    case = prepare(billing_case())
    best = case.scenario("B", "optimistic")
    expected = case.scenario("B", "expected")
    worst = case.scenario("B", "pessimistic")
    assert best is not None and best.headline == "$91,200 benefit"
    assert expected is not None and expected.headline == "$74,400 benefit"
    assert worst is not None and worst.headline == "$39,600 benefit"
    assert worst.headline != expected.headline

    names = {item.name for item in case.scenarios if item.option_key == "B"}
    assert set(STRESS_CASES) <= names

    shortage = case.scenario("B", "resource_shortage")
    assert shortage is not None and not shortage.feasible
    assert "headcount" in shortage.block_codes

    slip = case.scenario("B", "timeline_slippage")
    assert slip is not None and "timeline" in slip.block_codes

    dependency = case.scenario("B", "dependency_failure")
    assert dependency is not None and dependency.feasible
    assert "halfway" in dependency.detail

    loss = case.scenario("A", "unexpected_cost")
    assert loss is not None and loss.headline.endswith("loss")


def test_the_engine_traces_the_capacity_cut_without_inventing_a_new_call():
    text = render_engine(prepare(billing_case()))
    assert "Best case" in text
    assert "$91,200 benefit" in text
    assert "Expected case" in text
    assert "$74,400 benefit" in text
    assert "Worst case" in text
    assert "$39,600 benefit" in text
    assert "Needs 9 weeks and the limit is 8 weeks." in text
    assert "Customer adoption" in text
    assert "Market conditions" in text
    assert "Not on record. No budget limit is stored, and labor is unknown." in text
    assert "2 incidents a quarter" in text
    assert "5 engineers → 3 engineers" in text
    assert "8 weeks → 13 weeks" in text
    assert "Cost increases" in text
    assert "$33,969 → $55,200" in text
    assert "ROI decreases" in text
    assert "$62,954 benefit → $55,800 benefit" in text
    assert "Recommendation stays" in text
    assert "B. Partial migration → B. Partial migration" in text
    assert "Recommendation changes" not in text

    asked = ask([prepare(billing_case())], "What happens if our assumptions change?")
    assert asked.startswith("What happens if our assumptions change?")
    assert "Recommendation stays" in asked


def test_an_unscored_decision_does_not_invent_a_chain(tmp_path):
    agent = DecisionAgent(tmp_path)
    case = agent.register(FLUTTER)
    text = agent.scenarios(case.id)
    assert "Not scored yet." in text
    assert "Nothing is scored yet, so a change in assumptions cannot be traced." in text
    assert "5 engineers" not in text
    assert "$33,969" not in text
