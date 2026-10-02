from decision.demo import billing_case
from decision.loop import prepare
from decision.simulate import STRESS_CASES


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
