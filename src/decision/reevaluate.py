"""Watch a decision after new evidence arrives.

New evidence is checked against the assumptions, the risks, and the expected
outcome. If any of those move, confidence drops one step and the decision
goes back to a person.
"""

from datetime import date

from decision.brief import write_brief
from decision.errors import DecisionError
from decision.models import Constraint, DecisionCase, Evidence, Reevaluation, Stage
from decision.risk import build_risks
from decision.simulate import build_bands, build_scenarios, is_modeled
from decision.text import plain


def payments_regulation() -> Evidence:
    """The worked example: a regulation retires the no-downtime assumption."""

    return Evidence(
        id="payments-regulation",
        kind="regulation",
        statement=(
            "A new payments regulation requires a scheduled production window for billing changes. "
            "The no-downtime rule no longer holds."
        ),
        source="Payments regulation",
        channel="documentation",
        observed_at=date(2026, 10, 2),
        confidence=0.86,
        challenges="downtime",
        limit=1,
    )


def incorporate(case: DecisionCase, evidence: Evidence) -> DecisionCase:
    if any(item.id == evidence.id for item in case.evidence):
        raise DecisionError("That evidence is already on the decision.")
    if not evidence.statement.strip():
        raise DecisionError("Evidence needs a statement.")
    if not evidence.challenges or case.brief is None or not is_modeled(case):
        return case.model_copy(update={"evidence": [*case.evidence, evidence]})

    updated = _with_challenge(case, evidence)
    scenarios = build_scenarios(updated)
    bands = build_bands(updated)
    risks = build_risks(updated, scenarios, bands)
    brief = write_brief(updated, scenarios, bands, risks)
    review = _review(case, updated, evidence, scenarios, brief.recommendation_key)
    if review is None:
        return case.model_copy(update={"evidence": [*case.evidence, evidence]})
    text = brief.text.replace(
        f"Confidence is {brief.confidence}",
        f"Confidence is {review.confidence_after}",
        1,
    )
    brief = brief.model_copy(update={"confidence": review.confidence_after, "text": text})
    return updated.model_copy(
        update={
            "scenarios": scenarios,
            "bands": bands,
            "risks": risks,
            "brief": brief,
            "status": Stage.briefed,
            "reevaluations": [*case.reevaluations, review],
        }
    )


def render_review(item: Reevaluation, decision: str = "") -> str:
    original = decision or "The recorded decision"
    return (
        "Original decision\n"
        f"{original}\n\n"
        "New evidence\n"
        f"{item.statement}\n\n"
        "Assumption\n"
        f"{item.assumption}\n\n"
        "Risk\n"
        f"{item.risk}\n\n"
        "Expected outcome\n"
        f"{item.outcome}\n\n"
        "Confidence\n"
        f"{item.confidence_before} → {item.confidence_after}\n\n"
        "Re-evaluate\n"
        "Human review required.\n"
    )


def _review(
    before: DecisionCase,
    after: DecisionCase,
    evidence: Evidence,
    scenarios,
    new_key: str | None,
) -> Reevaluation | None:
    assumption, assumption_changed = _assumption(before, evidence)
    risk, risk_changed = _risk(before, scenarios)
    outcome, outcome_changed = _outcome(before, scenarios, new_key)
    if not (assumption_changed or risk_changed or outcome_changed):
        return None
    previous = before.brief.confidence if before.brief else "low"
    return Reevaluation(
        evidence_id=evidence.id,
        statement=evidence.statement,
        assumption=assumption,
        risk=risk,
        outcome=outcome,
        confidence_before=previous,
        confidence_after=_drop(previous),
    )


def _assumption(case: DecisionCase, evidence: Evidence) -> tuple[str, bool]:
    current = next((item for item in case.constraints if item.kind == evidence.challenges), None)
    new_limit = _limit_for(evidence)
    if current is not None and current.limit == new_limit:
        return f"The {evidence.challenges} assumption is unchanged.", False
    if evidence.challenges == "downtime" and (current is None or current.limit == 0) and new_limit != 0:
        return (
            "The assumption that production downtime is forbidden is no longer valid. "
            + evidence.statement
        ), True
    if evidence.challenges == "downtime" and new_limit == 0:
        return "Production downtime is now forbidden. " + evidence.statement, True
    previous = plain(current.limit) if current and current.limit is not None else "unset"
    if evidence.challenges == "timeline":
        return (
            f"The timeline assumption changed from {previous} weeks to {plain(new_limit)} weeks. "
            + evidence.statement
        ), True
    return (
        f"The staffing assumption changed from {previous} engineers to {plain(new_limit)} engineers. "
        + evidence.statement
    ), True


def _risk(case: DecisionCase, scenarios) -> tuple[str, bool]:
    notes: list[str] = []
    for option in case.options:
        previous = case.scenario(option.key, "expected")
        current = next(
            (item for item in scenarios if item.option_key == option.key and item.name == "expected"),
            None,
        )
        if previous is None or current is None or previous.block_codes == current.block_codes:
            continue
        dropped = [code for code in previous.block_codes if code not in current.block_codes]
        added = [code for code in current.block_codes if code not in previous.block_codes]
        if dropped:
            notes.append(f"{option.name} is no longer blocked by {_join(dropped)}.")
        if added:
            notes.append(f"{option.name} is now blocked by {_join(added)}.")
    if not notes:
        return "Risk is unchanged.", False
    return "Risk changed. " + " ".join(notes), True


def _outcome(case: DecisionCase, scenarios, new_key: str | None) -> tuple[str, bool]:
    old_key = case.brief.recommendation_key if case.brief else None
    old = case.scenario(old_key, "expected") if old_key else None
    new = next(
        (item for item in scenarios if item.option_key == new_key and item.name == "expected"),
        None,
    )
    old_headline = old.headline if old else "no estimate"
    new_headline = new.headline if new else "no estimate"
    if old_key != new_key:
        return (
            "The expected outcome changed. The recommendation moves from "
            f"{_name(case, old_key)} to {_name(case, new_key)}."
        ), True
    if old_headline != new_headline:
        return f"The expected outcome changed from {old_headline} to {new_headline}.", True
    return f"The expected outcome is unchanged at {old_headline}.", False


def _with_challenge(case: DecisionCase, evidence: Evidence) -> DecisionCase:
    limit = _limit_for(evidence)
    constraints: list[Constraint] = []
    found = False
    for item in case.constraints:
        if item.kind != evidence.challenges:
            constraints.append(item)
            continue
        found = True
        constraints.append(item.model_copy(update={"limit": limit, "statement": _statement(evidence, limit)}))
    if not found:
        constraints.append(
            Constraint(
                id=evidence.challenges,
                statement=_statement(evidence, limit),
                kind=evidence.challenges,
                limit=limit,
            )
        )
    return case.model_copy(update={"constraints": constraints, "evidence": [*case.evidence, evidence]})


def _limit_for(evidence: Evidence) -> float:
    if evidence.challenges == "downtime":
        return 0 if evidence.limit == 0 else 1
    if evidence.limit is None:
        raise DecisionError("That assumption needs a number.")
    return evidence.limit


def _statement(evidence: Evidence, limit: float) -> str:
    if evidence.challenges == "downtime":
        return "No production downtime" if limit == 0 else "Production downtime is allowed"
    if evidence.challenges == "timeline":
        return f"{plain(limit)}-week timeline"
    noun = "engineer" if limit == 1 else "engineers"
    return f"{plain(limit)} {noun} available"


def _drop(level: str) -> str:
    order = ["high", "medium", "low"]
    if level not in order:
        return "low"
    return order[min(order.index(level) + 1, len(order) - 1)]


def _name(case: DecisionCase, key: str | None) -> str:
    if key is None:
        return "no recommendation"
    option = case.option(key)
    if option is None:
        return key
    return f"{option.key}. {option.name}"


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
