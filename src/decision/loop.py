"""One pass from a request to a brief, then the human steps after it."""

from decision.alternatives import complete_alternatives
from decision.brief import write_brief
from decision.errors import DecisionError
from decision.execute import execution_plan
from decision.frame import decision_line, default_metrics, is_migration
from decision.learn import build_outcomes, priors_from, write_lesson
from decision.models import DecisionCase, Option, Prior, Stage
from decision.reevaluate import outcome_trigger
from decision.risk import build_risks
from decision.simulate import build_bands, build_scenarios, is_modeled

HUMAN = {Stage.deferred, Stage.rejected, Stage.executing, Stage.tracking, Stage.learned}
AFTER_APPROVAL = {Stage.executing, Stage.tracking, Stage.learned}


def prepare(case: DecisionCase) -> DecisionCase:
    pattern = "migration" if is_migration(case.request) else "general"
    updated = case.model_copy(
        update={
            "pattern": pattern,
            "decision": decision_line(case.request, case.subject),
            "options": complete_alternatives(case.options, pattern),
            "metrics": case.metrics or (default_metrics() if pattern == "migration" else []),
        }
    )
    if not is_modeled(updated):
        return updated.model_copy(
            update={
                "status": Stage.framed,
                "scenarios": [],
                "bands": [],
                "risks": [],
                "brief": None,
            }
        )
    scenarios = build_scenarios(updated)
    bands = build_bands(updated)
    risks = build_risks(updated, scenarios, bands)
    brief = write_brief(updated, scenarios, bands, risks)
    return updated.model_copy(
        update={
            "scenarios": scenarios,
            "bands": bands,
            "risks": risks,
            "brief": brief,
            "status": Stage.briefed,
        }
    )


def gaps(case: DecisionCase) -> list[str]:
    missing: list[str] = []
    if not case.objective.strip():
        missing.append("An objective")
    if not case.constraints:
        missing.append("Constraints")
    if not case.options:
        missing.append("Options")
    if not case.evidence:
        missing.append("Evidence")
    if not is_modeled(case):
        missing.append("An estimate for every option")
    return missing


def apply_review(
    case: DecisionCase,
    action: str,
    note: str,
    reviewed_at: str,
    approved_by: str = "",
    option_key: str = "",
) -> DecisionCase:
    if action not in {"approved", "rejected", "deferred", "modified"}:
        raise DecisionError("Review action must be approved, rejected, deferred, or modified.")
    if not note.strip():
        raise DecisionError("Record the reasoning for this decision.")
    if case.status not in {Stage.briefed, Stage.deferred}:
        raise DecisionError("This decision is not waiting for a person.")
    if action == "approved":
        option = _recommended_option(case)
        return _decided(case, action, note, reviewed_at, approved_by, option, option.key)
    if action == "modified":
        option = _modified_option(case, option_key)
        return _decided(case, action, note, reviewed_at, approved_by, option, option.key)
    return case.model_copy(
        update={
            "status": Stage.rejected if action == "rejected" else Stage.deferred,
            "review_action": action,
            "review_note": note.strip(),
            "reviewed_at": reviewed_at,
            "approved_by": approved_by.strip(),
            "human_choice": "",
            "execution": [],
        }
    )


def _recommended_option(case: DecisionCase) -> Option:
    if case.brief is None or case.brief.recommendation_key is None:
        raise DecisionError("This decision is framed and not ready to approve.")
    option = case.option(case.brief.recommendation_key)
    if option is None:
        raise DecisionError("The recommended option is missing.")
    return option


def _modified_option(case: DecisionCase, option_key: str) -> Option:
    recommended = _recommended_option(case)
    key = option_key.strip()
    if not key:
        raise DecisionError("Modify names an option already on this decision.")
    option = case.option(key)
    if option is None:
        raise DecisionError("That option is not on this decision.")
    if option.key == recommended.key:
        raise DecisionError("That is the recommendation. Approve it, or choose another option on the record.")
    return option


def _decided(
    case: DecisionCase,
    action: str,
    note: str,
    reviewed_at: str,
    approved_by: str,
    option: Option,
    choice: str,
) -> DecisionCase:
    updated = case.model_copy(
        update={
            "status": Stage.executing,
            "review_action": action,
            "review_note": note.strip(),
            "reviewed_at": reviewed_at,
            "approved_by": approved_by.strip(),
            "human_choice": choice,
            "execution": execution_plan(case, option),
        }
    )
    from decision.impact import attach_impact_trigger

    return attach_impact_trigger(updated)


def complete_step(case: DecisionCase, step_id: str) -> DecisionCase:
    if case.status not in AFTER_APPROVAL:
        raise DecisionError("Approve the decision before executing it.")
    if not any(step.id == step_id for step in case.execution):
        raise DecisionError(f"No execution step named {step_id}.")
    steps = [
        step.model_copy(update={"status": "done"}) if step.id == step_id else step
        for step in case.execution
    ]
    return case.model_copy(update={"execution": steps})


def record_outcomes(case: DecisionCase, actuals: dict[str, float]) -> DecisionCase:
    if case.status not in AFTER_APPROVAL:
        raise DecisionError("Approve the decision before recording an outcome.")
    if case.execution and any(step.status != "done" for step in case.execution):
        raise DecisionError("Finish the execution plan before recording an outcome.")
    missing = [metric.name for metric in case.metrics if metric.id not in actuals]
    if missing:
        raise DecisionError("Enter a number for each success metric: " + ", ".join(missing) + ".")
    outcomes = build_outcomes(case, actuals)
    if len(outcomes) != len(case.metrics):
        raise DecisionError("The recommended option has no estimate to compare against.")
    return case.model_copy(update={"outcomes": outcomes, "status": Stage.tracking, "lesson": None})


def learn(case: DecisionCase) -> tuple[DecisionCase, list[Prior]]:
    if case.status != Stage.tracking or not case.outcomes:
        raise DecisionError("Record the outcome before writing the lesson.")
    lesson = write_lesson(case)
    updated = case.model_copy(update={"lesson": lesson, "status": Stage.learned})
    review = outcome_trigger(updated)
    if review is not None and updated.brief is not None:
        text = updated.brief.text.replace(
            f"Confidence is {updated.brief.confidence}",
            f"Confidence is {review.confidence_after}",
            1,
        )
        brief = updated.brief.model_copy(update={"confidence": review.confidence_after, "text": text})
        updated = updated.model_copy(
            update={"brief": brief, "reevaluations": [*updated.reevaluations, review]}
        )
    elif review is not None:
        updated = updated.model_copy(update={"reevaluations": [*updated.reevaluations, review]})
    return updated, priors_from(updated)
