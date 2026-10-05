from decision.demo import OBSERVED, billing_case
from decision.frame import constraint_set
from decision.graph import ask
from decision.impact import render_impact
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes
from decision.reevaluate import incorporate, payments_regulation


def test_partial_migration_maps_only_recorded_effects():
    case = prepare(billing_case())
    text = render_impact(case)
    assert "├── Service" in text
    assert "Billing service" in text
    assert "Invoice pipeline" in text
    assert "├── Engineering" in text
    assert "47 minutes → 12 minutes" in text
    assert "├── Operations" in text
    assert "6 incidents per quarter → 2 incidents per quarter" in text
    assert "├── Business" in text
    assert "$18,400 per month → $12,200 per month" in text
    assert "$74,400 benefit" in text
    assert "└── Goal" in text
    assert "Reduce operational cost and deployment time." in text
    assert "Checkout" not in text
    assert "Subscriptions" not in text
    assert "Payment credentials" not in text
    assert "affects → Billing service" in text
    assert "affects → Invoice pipeline" in text
    assert "depends_on → Partial migration is estimated at 6 weeks." in text
    assert "depends_on → 3 engineers are available." in text
    assert "depends_on → The timeline limit is 8 weeks." in text
    assert "depends_on → Production downtime is forbidden." in text
    assert "conflicts_with" not in text
    assert "uses all 3 available engineers" in text
    assert "Full migration needs 5 and stays blocked." in text
    assert "Removing the fallback path early would break the no-downtime rule." in text
    assert "Invoice delays after billing deploys are a recurring support theme." in text
    assert "No separate measure of those delays is on record." in text
    assert "No other stored decision is affected." in text
    assert "this goal still holds." in text
    assert "Service impact:" in text
    assert "Engineering impact:  High" in text
    assert "Operations impact:   High" in text
    assert "Business impact:     Medium" in text
    assert "Goal impact:         High" in text
    assert "Overall impact:      High" in text
    assert "Severity" in text
    assert "Probability" in text
    assert "Scope" in text
    assert "Reversibility" in text
    assert "Confidence" in text
    assert "Expected return, 58%." in text
    assert "Invoice shadow read, 74%." in text
    assert "Product impact" not in text
    assert "Security impact" not in text
    assert "Goal affected?" in text
    assert "Subgoal affected?" in text
    assert "Plan affected?" in text
    assert "Agent action required?" in text
    assert "Put a strangler facade in front of the service. Weeks 1–2." in text
    assert "The plan has not started." in text
    assert "Human approval required. The agent does not start the plan." in text
    assert "Decision Impact Analysis" in text
    assert "Significant impact detected" in text
    assert "Yes. Engineering, Operations, and the goal are high." in text
    assert "Affected goal/plan identified" in text
    assert "No re-evaluation is triggered. The high impact is already in the brief." in text
    assert "The recommendation stays. The plan has not started." in text


def test_the_two_impact_questions_use_the_billing_record():
    case = prepare(billing_case())
    changed = ask([case], "If we make this decision, what else changes?")
    assert "Deployment time moves from 47 minutes to 12 minutes." in changed
    assert "move the invoice pipeline behind a strangler facade." in changed
    assert "Engineering capacity." in render_impact(case)
    assert "depends_on" not in changed
    assert "Partial migration is estimated at 6 weeks." in changed

    invalidated = ask(
        [case],
        "Which existing goals, plans, assumptions, and decisions could this invalidate?",
    )
    assert "B. Partial migration breaks none of the assumptions it depends on." in invalidated
    assert "The worst case needs 9 weeks and the limit is 8 weeks." in invalidated
    assert "No stored plan is invalidated." in invalidated
    assert "No other stored decision is affected." in invalidated
    assert "What evidence would invalidate" not in invalidated


def test_a_second_decision_on_the_same_service_conflicts():
    billing = prepare(billing_case())
    cutover = prepare(
        billing_case().model_copy(update={"id": "billing-cutover", "subject": "billing"})
    )
    cutover = apply_review(
        cutover,
        "modified",
        "The downtime window is open this quarter.",
        "2026-10-02T00:00:00+00:00",
        "Platform",
        option_key="C",
    )
    search = prepare(
        billing_case().model_copy(
            update={
                "id": "search-migration",
                "subject": "search",
                "constraints": constraint_set(3, 8, False),
            }
        )
    )
    text = render_impact(billing, [billing, cutover, search])
    assert "conflicts_with → billing-cutover (C. Full migration)" in text
    assert "search-migration" not in text
    invalidated = ask(
        [billing, cutover, search],
        "Which existing goals, plans, assumptions, and decisions could this invalidate?",
        billing.id,
    )
    assert "billing-cutover chooses C. Full migration" in invalidated
    assert "search-migration" not in invalidated
    assert "Staff the engineers the full migration requires." in invalidated


def test_a_regulation_triggers_re_evaluation_from_the_impact():
    case = incorporate(prepare(billing_case()), payments_regulation())
    text = render_impact(case)
    assert "Re-evaluation triggered" in text
    assert "Current evidence requires a production window. Re-evaluation recommended." in text
    assert "B. Partial migration. The recommendation stays." in text
    assert "The plan is not replaced until a person reviews this update." in text
    assert case.reevaluations[-1].kind == "evidence"


def test_a_material_outcome_updates_the_estimate_and_leaves_the_plan():
    case = prepare(billing_case())
    approved = apply_review(case, "approved", "Ship the invoice slice", "2026-10-02T00:00:00+00:00", "Platform")
    assert approved.reevaluations == []
    for step in list(approved.execution):
        approved = complete_step(approved, step.id)
    tracked = record_outcomes(approved, OBSERVED)
    learned, _priors = learn(tracked)
    text = render_impact(learned)
    assert "The recorded result is 15 minutes. Re-evaluation recommended." in text
    assert "The execution plan already run stays in place." in text
    assert [step.id for step in learned.execution] == ["facade", "slice", "cutover"]


def test_full_migration_would_break_the_assumptions_it_depends_on():
    case = prepare(billing_case())
    chosen = apply_review(
        case,
        "modified",
        "The downtime window is open this quarter.",
        "2026-10-02T00:00:00+00:00",
        "Platform",
        option_key="C",
    )
    text = ask([chosen], "Which existing goals, plans, assumptions, and decisions could this invalidate?")
    assert (
        "C. Full migration would break these assumptions: 3 engineers are available, "
        "the timeline limit is 8 weeks, and production downtime is forbidden."
    ) in text
    scored = render_impact(chosen)
    assert "Reversibility   Low. Not reversible." in scored
    assert "Agent action required. The plan is running, and C. Full migration would break these assumptions:" in scored
    assert chosen.reevaluations[-1].kind == "impact"
    assert "Re-evaluation triggered" in scored
    assert "The plan waits until a person confirms this impact." in scored
    from decision.reevaluate import accept_revision

    accepted = accept_revision(chosen, "The downtime window is open this quarter.", "Platform")
    assert [step.id for step in accepted.execution] == ["staff", "window", "extract"]
    assert accepted.reevaluations[-1].accepted_note == "The downtime window is open this quarter."
