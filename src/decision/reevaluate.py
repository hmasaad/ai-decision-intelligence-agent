"""Watch a decision after it has been made.

New evidence, a moved risk, a changed assumption or constraint, or an actual
outcome that misses the material line sends the decision back to a person.
The agent recommends again. It does not approve the revision itself.
"""

from datetime import date

from decision.brief import write_brief
from decision.errors import DecisionError
from decision.models import Constraint, DecisionCase, Evidence, Reevaluation, Stage
from decision.risk import build_risks
from decision.simulate import build_bands, build_scenarios, is_modeled
from decision.text import format_amount, plain


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
    old_key = before.brief.recommendation_key if before.brief else None
    return Reevaluation(
        evidence_id=evidence.id,
        statement=evidence.statement,
        assumption=assumption,
        risk=risk,
        outcome=outcome,
        confidence_before=previous,
        confidence_after=_drop(previous),
        kind="evidence",
        trigger=_trigger_sentence(before, evidence),
        recommendation=_recommendation_line(before, old_key, new_key),
    )


def outcome_trigger(case: DecisionCase) -> Reevaluation | None:
    """A material miss on the recorded outcome, if the lesson asked for one."""

    if case.lesson is None or not case.lesson.reevaluate:
        return None
    if any(item.kind == "outcome" for item in case.reevaluations):
        return None
    triggers = _outcome_triggers(case)
    if not triggers:
        return None
    previous = case.brief.confidence if case.brief else "low"
    key = case.human_choice or (case.brief.recommendation_key if case.brief else "")
    stayed = _name(case, key or None)
    revision = " ".join(case.lesson.revisions)
    recommendation = f"{stayed}. The recommendation stays."
    if revision:
        recommendation = f"{recommendation} {revision}"
    broke = next((line for line in case.lesson.statements if "broke" in line), "")
    return Reevaluation(
        evidence_id="outcome",
        statement=triggers[0],
        assumption=broke or "No assumption was retired by the outcome.",
        risk="Risk is unchanged.",
        outcome=" ".join(triggers),
        confidence_before=previous,
        confidence_after=_drop(previous),
        kind="outcome",
        trigger=triggers[0],
        recommendation=recommendation,
    )


def accept_revision(case: DecisionCase, note: str, by: str) -> DecisionCase:
    """Record that a person accepted an outcome revision. Execution stays as it was."""

    if not note.strip():
        raise DecisionError("Record the reasoning for this decision.")
    if not case.reevaluations:
        raise DecisionError("Nothing is waiting for a revision review.")
    last = case.reevaluations[-1]
    if last.kind not in {"outcome", "impact"}:
        raise DecisionError("This re-evaluation is waiting on the decision form.")
    if last.accepted_note:
        raise DecisionError("This revision was already accepted.")
    updated = last.model_copy(update={"accepted_by": by.strip(), "accepted_note": note.strip()})
    return case.model_copy(update={"reevaluations": [*case.reevaluations[:-1], updated]})


class Watch:
    def __init__(self, label: str, detail: str) -> None:
        self.label = label
        self.detail = detail


def monitor(case: DecisionCase) -> list[Watch]:
    """The five things that can send this decision back to a person."""

    evidence = [item for item in case.reevaluations if item.kind == "evidence"]
    outcomes = [item for item in case.reevaluations if item.kind == "outcome"]
    risk = next(
        (item.risk for item in reversed(case.reevaluations) if item.risk.startswith("Risk changed")),
        "No risk block has moved.",
    )
    assumption = next(
        (
            item.assumption
            for item in reversed(case.reevaluations)
            if item.kind == "evidence" and "unchanged" not in item.assumption
        ),
        "No assumption has been retired.",
    )
    constraint = evidence[-1].trigger if evidence else "No constraint limit has moved."
    if outcomes:
        actual = outcomes[-1].trigger
    elif case.outcomes:
        actual = "The recorded outcome stays inside the material line."
    else:
        actual = (
            "No outcome is recorded yet. A miss of 25% or more on deployment time "
            "or infrastructure cost, or a broken constraint, comes back to a person."
        )
    return [
        Watch(
            "New evidence",
            evidence[-1].statement if evidence else "No new evidence has challenged an assumption.",
        ),
        Watch("New risks", risk),
        Watch("Changed assumptions", assumption),
        Watch("Changed constraints", constraint),
        Watch("Actual outcomes", actual),
    ]


def render_watch(case: DecisionCase) -> str:
    lines = ["Monitor", ""]
    for item in monitor(case):
        lines.append(item.label)
        lines.append(item.detail)
        lines.append("")
    for item in case.reevaluations:
        lines.append(render_chain(case, item).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_chain(case: DecisionCase, item: Reevaluation) -> str:
    steps = [
        ("Decision", case.decision or "Not stated."),
        ("Trigger detected", item.trigger or item.statement),
        ("Re-evaluate", _reevaluate_body(item)),
        ("New recommendation", item.recommendation or "Not recommended yet."),
        ("Human approval", approval_line(case, item)),
    ]
    lines: list[str] = []
    for index, (label, detail) in enumerate(steps):
        lines.append(label)
        lines.append(detail)
        if index < len(steps) - 1:
            lines.append("↓")
    return "\n".join(lines).rstrip() + "\n"


def approval_line(case: DecisionCase, item: Reevaluation) -> str:
    if item.kind in {"outcome", "impact"} and item.accepted_note:
        who = item.accepted_by or "A person whose name was not recorded"
        return f"Accepted by {who}. Reasoning: {item.accepted_note}."
    if item.kind == "impact":
        return (
            "Human approval is required. "
            "The plan waits until a person confirms this impact."
        )
    if item.kind == "outcome":
        return (
            "Human approval is required. "
            "A person accepts this revision before the next decision of this pattern."
        )
    return (
        "Human approval is required. "
        "The earlier decision stands until a person reviews this update."
    )


def _trigger_sentence(case: DecisionCase, evidence: Evidence) -> str:
    current = next((item for item in case.constraints if item.kind == evidence.challenges), None)
    new_limit = _limit_for(evidence)
    previous = plain(current.limit) if current and current.limit is not None else ""
    if evidence.challenges == "headcount":
        assumed = f"{previous} engineers" if previous else "no recorded headcount"
        return (
            f"The original decision assumed {assumed}. "
            f"Current capacity is now {plain(new_limit)}. "
            "Re-evaluation recommended."
        )
    if evidence.challenges == "timeline":
        assumed = f"{previous} weeks" if previous else "no recorded timeline"
        return (
            f"The original decision assumed {assumed}. "
            f"Current timeline is now {plain(new_limit)} weeks. "
            "Re-evaluation recommended."
        )
    if evidence.challenges == "downtime" and new_limit != 0:
        return (
            "The original decision assumed no production downtime. "
            "Current evidence requires a production window. "
            "Re-evaluation recommended."
        )
    if evidence.challenges == "downtime":
        return (
            "The original decision allowed production downtime. "
            "Current evidence forbids it. "
            "Re-evaluation recommended."
        )
    return evidence.statement + " Re-evaluation recommended."


def _recommendation_line(case: DecisionCase, old_key: str | None, new_key: str | None) -> str:
    if old_key == new_key:
        return f"{_name(case, new_key)}. The recommendation stays."
    return f"The recommendation moves from {_name(case, old_key)} to {_name(case, new_key)}."


def _outcome_triggers(case: DecisionCase) -> list[str]:
    lines: list[str] = []
    for outcome in case.outcomes:
        metric = case.metric(outcome.metric_id)
        if metric is None or outcome.worse_by < 0.25 or metric.weight < 1.5:
            continue
        lines.append(
            f"The original decision expected {metric.name.lower()} of {format_amount(metric, outcome.predicted)}. "
            f"The recorded result is {format_amount(metric, outcome.actual)}. "
            "Re-evaluation recommended."
        )
    if case.lesson is not None:
        for line in case.lesson.statements:
            if "broke" in line:
                lines.append(f"{line} Re-evaluation recommended.")
    return lines


def _reevaluate_body(item: Reevaluation) -> str:
    return " ".join(
        part
        for part in (
            item.assumption,
            item.risk,
            item.outcome,
            f"Confidence {item.confidence_before} → {item.confidence_after}.",
        )
        if part
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
