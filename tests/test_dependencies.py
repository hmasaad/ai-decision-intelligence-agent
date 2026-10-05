from decision.demo import billing_case
from decision.dependencies import render_dependencies
from decision.frame import constraint_set
from decision.loop import apply_review, prepare


def test_one_decision_has_no_dependency_edge():
    case = prepare(billing_case())
    text = render_dependencies([case], case.id)
    assert "billing-migration" in text
    assert "No other stored decision is linked." in text
    assert "enables →" not in text
    assert "Payment Provider" not in text
    assert "Subscription" not in text


def test_a_full_migration_choice_blocks_conflicts_and_invalidates():
    billing = prepare(billing_case())
    cutover = apply_review(
        prepare(billing_case().model_copy(update={"id": "billing-cutover", "subject": "billing"})),
        "modified",
        "The downtime window is open this quarter.",
        "2026-10-02T00:00:00+00:00",
        "Platform",
        option_key="C",
    )
    search = prepare(
        billing_case().model_copy(
            update={"id": "search-migration", "subject": "search", "constraints": constraint_set(3, 8, False)}
        )
    )
    text = render_dependencies([billing, cutover, search], billing.id)
    assert "blocks → billing-cutover" in text
    assert "conflicts_with → billing-migration" in text or "conflicts_with → billing-cutover" in text
    assert "invalidates → billing-migration" in text
    assert "Critical" in text
    assert "Failure of billing-cutover will invalidate billing-migration." in text
    assert "search-migration" not in text
    assert "Needs 5 engineers and 3 are available." in text
    assert "Requires production downtime." in text
    assert "No evidence is on record for the 8-week timeline." in text
    assert "Relationship type  blocks" in text
    assert "Relationship type  invalidates" in text
    assert "Strength           High" in text


def test_room_for_full_migration_enables_it_and_is_a_critical_dependency():
    blocked = apply_review(
        prepare(billing_case().model_copy(update={"id": "billing-cutover", "subject": "billing"})),
        "modified",
        "The downtime window is open this quarter.",
        "2026-10-02T00:00:00+00:00",
        "Platform",
        option_key="C",
    )
    opener = prepare(
        billing_case().model_copy(
            update={
                "id": "billing-capacity",
                "subject": "billing",
                "constraints": constraint_set(5, 14, False),
            }
        )
    )
    text = render_dependencies([blocked, opener], blocked.id)
    assert "depends_on → billing-capacity" in text
    assert "critically depends on billing-capacity, and failure of billing-capacity will invalidate C. Full migration." in text
    assert "Critical" in text
    opener_text = render_dependencies([blocked, opener], opener.id)
    assert "enables → billing-cutover" in opener_text
    assert "Admits C. Full migration." in opener_text
