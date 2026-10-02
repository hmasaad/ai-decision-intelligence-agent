from decision.demo import billing_case
from decision.loop import prepare


def _judgment(case, judgment_id):
    from decision.uncertainty import judgments

    return next(item for item in judgments(case) if item.id == judgment_id)


def test_figures_keep_a_stance_and_a_confidence():
    case = prepare(billing_case())
    expected = _judgment(case, "return")
    duration = _judgment(case, "duration")
    cost = _judgment(case, "cost")
    current = _judgment(case, "current_infra_cost")
    engineers = _judgment(case, "engineers")
    timeline = _judgment(case, "timeline")
    labor = _judgment(case, "labor")

    assert expected.display == "$74,400 benefit a year"
    assert expected.stance == "inferred"
    assert expected.percent == "58%"

    assert duration.display == "6–9 weeks"
    assert duration.stance == "estimated"
    assert duration.percent == "58%"

    assert cost.display == "$10,800–$15,100 per month"
    assert cost.stance == "estimated"
    assert cost.percent == "58%"

    assert current.display == "$18,400 per month"
    assert current.stance == "known"
    assert current.percent == "88%"

    assert engineers.stance == "known"
    assert engineers.percent == "80%"
    assert timeline.stance == "assumed"
    assert timeline.confidence is None
    assert labor.stance == "unknown"
    assert labor.display == "Unknown"

    assert "inferred, with 58% confidence" in case.brief.text
