from decision.demo import billing_case
from decision.loop import prepare
from decision.whatif import answer, posed


def _step(item, label):
    return next(step for step in item.steps if step.label == label)


def test_a_capacity_cut_stretches_the_timeline_and_lowers_the_return():
    case = prepare(billing_case())
    item = posed(case)
    assert item is not None
    assert item.question == "What happens if engineering capacity changes from 5 to 3?"
    assert _step(item, "Engineering capacity").before == "5 engineers"
    assert _step(item, "Engineering capacity").after == "3 engineers"
    assert _step(item, "Timeline").before == "8 weeks"
    assert _step(item, "Timeline").after == "13 weeks"
    assert "assumed" in _step(item, "Timeline").note

    cost = _step(item, "Migration cost")
    assert cost.before == "$33,969"
    assert cost.after == "$55,200"
    assert "increases" in cost.note

    returned = _step(item, "Expected return")
    assert returned.before == "$62,954 benefit"
    assert returned.after == "$55,800 benefit"
    assert "decreases" in returned.note
    assert "$74,400 benefit" in returned.note

    confidence = _step(item, "Decision confidence")
    assert confidence.before == "58%"
    assert confidence.after == "49%"
    assert item.changed is False
    assert item.recommendation_after == "B. Partial migration"


def test_room_for_the_full_migration_changes_the_call():
    case = prepare(billing_case())
    item = answer(
        case,
        from_engineers=3,
        engineers=5,
        from_weeks=8,
        weeks=14,
        downtime_forbidden=False,
    )
    assert item is not None
    assert item.changed is True
    assert item.recommendation_before == "B. Partial migration"
    assert item.recommendation_after == "C. Full migration"
    assert "increases" in _step(item, "Expected return").note
    assert _step(item, "Expected return").after == "$75,415 benefit"
    assert _step(item, "Decision confidence").after == "33%"
    assert "downtime ban" in _step(item, "Decision confidence").note
