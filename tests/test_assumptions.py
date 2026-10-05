from decision.assumptions import answer, driving, render_assumptions
from decision.demo import billing_case
from decision.graph import ask
from decision.loop import prepare


def test_the_six_week_assumption_keeps_the_estimate_confidence():
    case = prepare(billing_case())
    items = driving(case)
    duration = items[0]
    assert duration.statement == "Partial migration is estimated at 6 weeks."
    assert duration.confidence == "58%"
    assert duration.impact == "High"
    assert "9 weeks" in duration.impact_detail
    assert "limit is 8 weeks" in duration.impact_detail
    assert duration.evidence.startswith("Architecture review, 58%.")
    assert "Platform retrospective recorded a partial migration in 7 weeks, at 70% confidence." in duration.evidence
    assert duration.option_name == "B. Partial migration"
    assert duration.recommendation == "B. Partial migration"

    text = render_assumptions(case)
    assert "Assumption" in text
    assert "        ↓" in text
    assert "Option" in text
    assert "Recommendation" in text
    assert "B. Partial migration" in text


def test_the_constraints_that_drive_the_choice_name_their_evidence():
    case = prepare(billing_case())
    by_statement = {item.statement: item for item in driving(case)}
    headcount = by_statement["3 engineers are available."]
    assert headcount.confidence == "80%"
    assert headcount.impact == "High"
    assert headcount.evidence.startswith("Staffing plan")
    timeline = by_statement["The timeline limit is 8 weeks."]
    assert timeline.confidence == "Assumed"
    assert timeline.evidence == "No evidence is on record."
    assert timeline.impact == "High"
    downtime = by_statement["Production downtime is forbidden."]
    assert downtime.confidence == "76%"
    assert downtime.impact == "Medium"
    assert "SRE (opinion)" in downtime.evidence
    assert "other blocks remain" in downtime.impact_detail


def test_driving_question_uses_the_tracker():
    case = prepare(billing_case())
    text = ask([case], "Which assumptions are driving this decision?")
    assert "Partial migration is estimated at 6 weeks." in text
    assert "58%" in text
    assert "Assumed" in text
    reply = answer(case, "Which assumptions are driving this decision?")
    assert reply.startswith("Which assumptions are driving this decision?")


def test_a_recorded_assumption_is_kept_when_it_is_not_scored():
    case = prepare(billing_case()).model_copy(
        update={"assumptions": ["Architecture X can host the current screens."]}
    )
    recorded = [item for item in case.assumptions]
    assert recorded == ["Architecture X can host the current screens."]
    from decision.assumptions import track

    extra = [item for item in track(case) if not item.driving]
    assert extra[0].statement == "Architecture X can host the current screens."
    assert extra[0].confidence == "Not recorded."
    assert extra[0].impact == "Not judged."
