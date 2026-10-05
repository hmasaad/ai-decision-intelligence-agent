from decision.demo import OBSERVED, billing_case
from decision.frame import constraint_set
from decision.graph import ask, render_graph
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes


def test_the_chain_names_what_supports_the_billing_decision():
    case = prepare(billing_case())
    text = render_graph(case)
    for title in (
        "EVIDENCE",
        "ASSUMPTION",
        "CONSTRAINT",
        "OPTION",
        "EXPECTED OUTCOME",
        "RISK",
        "DECISION",
        "ACTUAL OUTCOME",
        "LEARNING",
    ):
        assert title in text
    assert "Staffing plan" in text
    assert "Supports 3 engineers available." in text
    assert "SRE" in text
    assert "No evidence on record supports this assumption." in text
    assert "B. Partial migration" in text
    assert "C. Full migration" in text
    assert "$74,400 benefit" in text
    assert "Not recorded yet." in text
    assert "Not written yet." in text


def test_assumptions_responsible_for_the_recommendation():
    case = prepare(billing_case())
    answer = ask([case], "Which assumptions are responsible for this decision?")
    assert "3 engineers available" in answer
    assert "8-week timeline" in answer
    assert "No production downtime" in answer
    assert "Rests on Staffing plan." in answer
    assert "Rests on SRE." in answer
    assert "No evidence on record supports this assumption." in answer
    assert "Blocks Full migration." in answer


def test_invalidating_full_migration_takes_all_three_assumptions():
    case = prepare(billing_case())
    answer = ask([case], "What evidence would invalidate it?")
    assert "no evidence behind it" in answer
    assert "evidence that at least 5 engineers are available" in answer
    assert "evidence that the timeline is at least 14 weeks" in answer
    assert "evidence that production downtime is allowed" in answer
    assert "One of them leaves Full migration blocked" in answer


def test_only_decisions_that_use_the_assumption_are_returned():
    billing = prepare(billing_case())
    search = prepare(
        billing_case().model_copy(
            update={
                "id": "search-migration",
                "subject": "search",
                "constraints": constraint_set(3, 8, False),
            }
        )
    )
    answer = ask(
        [billing, search],
        "Which decisions depend on the no-downtime assumption?",
        billing.id,
    )
    assert "billing-migration" in answer
    assert "search-migration" not in answer
    assert "Full migration is blocked by it" in answer

    missing = ask([billing], "Which decisions depend on the PostgreSQL assumption?")
    assert missing.startswith("No stored decision depends on that assumption.")


def test_a_single_constraint_change_does_not_flip_the_call():
    case = prepare(billing_case())
    answer = ask([case], "What happens if the headcount constraint changes to 5?")
    assert "Only headcount changes." in answer
    assert "Recommendation stays: B. Partial migration → B. Partial migration" in answer


def test_changing_the_holding_constraints_together_is_traced():
    case = prepare(billing_case())
    answer = ask([case], "What happens if this constraint changes?")
    assert "changed together" in answer
    assert "Recommendation changes:" in answer
    assert "Partial migration → " in answer
    assert "Partial migration → Partial migration" not in answer


def test_the_graph_answers_why_the_billing_decision_was_made():
    case = prepare(billing_case())
    answer = ask([case], "Why was this decision made?")
    assert answer.startswith("Why was this decision made?")
    assert "B. Partial migration is the recommendation because this path reaches it." in answer
    assert "Full migration scores higher and is blocked by 3 engineers available, the 8-week timeline, and no production downtime." in answer
    assert "Its expected outcome is $74,400 benefit." in answer


def test_the_graph_names_the_evidence_that_supports_partial_migration():
    case = prepare(billing_case())
    answer = ask([case], "Which evidence supports it?")
    assert "3 pieces of evidence support B. Partial migration, while 0 contradict it." in answer
    assert "Architecture review, 58%." in answer
    assert "Invoice shadow read, 74%." in answer
    assert "Platform retrospective, 70%." in answer
    assert "Staffing plan, 80%. Supports 3 engineers are available." in answer
    assert "SRE (opinion), 76%." in answer
    assert "This claim is opinion." in answer
    assert "The timeline limit is 8 weeks. No evidence is on record for this assumption." in answer
    assert "integration" not in answer.lower()


def test_the_graph_names_the_assumptions_the_decision_depends_on():
    case = prepare(billing_case())
    answer = ask([case], "Which assumptions does it depend on?")
    assert "Partial migration is estimated at 6 weeks." in answer
    assert "3 engineers are available." in answer
    assert "The timeline limit is 8 weeks." in answer
    assert "Production downtime is forbidden." in answer
    assert "No stored decision depends on that assumption." not in answer


def test_the_graph_names_what_would_change_the_billing_decision():
    case = prepare(billing_case())
    answer = ask([case], "What would cause the decision to change?")
    assert "Full migration scores higher and is blocked by 3 engineers available, the 8-week timeline, and no production downtime." in answer
    assert "One of them leaves Full migration blocked" in answer
    assert "The recommendation moves to C. Full migration." in answer
    assert "Engineering capacity drops from 3 to 2 engineers." in answer
    assert "The recommendation moves to D. Managed billing service." in answer
    assert "5 engineers. Current capacity is now 3." not in answer


def test_the_chain_continues_through_the_recorded_outcome():
    case = prepare(billing_case())
    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00", "Platform")
    for step in approved.execution:
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)
    learned, _priors = learn(tracked)
    text = render_graph(learned)
    assert "Variance +25%." in text
    assert "Not written yet." not in text
    assert "25%" in text
