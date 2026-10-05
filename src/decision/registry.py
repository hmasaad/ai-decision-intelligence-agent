"""Persistent identity for a decision.

The registry stores the decision as a record: the goal, the question, the
context, and the fields around them. Inspect reads that record back. It does
not score options or fill in a recommendation that nobody recorded.
"""

import re

from decision.errors import DecisionError
from decision.models import Constraint, DecisionCase, Option, Stage
from decision.text import format_amount, slug

OPEN_STATUSES = (Stage.requested, Stage.framed, Stage.deferred, Stage.rejected)
_BLANK = "Not recorded."


def clean_question(question: str) -> str:
    cleaned = " ".join(question.strip().split())
    if not cleaned:
        raise DecisionError("A decision needs a question.")
    if not cleaned.endswith("?"):
        cleaned += "?"
    return cleaned[0].upper() + cleaned[1:]


def register_case(
    question: str,
    goal: str = "",
    context: str = "",
    owner: str = "",
    options: list[str] | None = None,
    constraints: list[str] | None = None,
    assumptions: list[str] | None = None,
    organization: str = "Workspace",
    case_id: str = "",
) -> DecisionCase:
    asked = clean_question(question)
    return DecisionCase(
        id=case_id or slug(asked),
        organization=organization.strip() or "Workspace",
        request=asked,
        decision=asked,
        objective=goal.strip(),
        context=context.strip(),
        owner=owner.strip(),
        assumptions=_lines(assumptions or []),
        options=parse_options(options or []),
        constraints=parse_constraints(constraints or []),
        pattern="general",
        status=Stage.requested,
    )


def apply_update(
    case: DecisionCase,
    *,
    goal: str | None = None,
    question: str | None = None,
    context: str | None = None,
    owner: str | None = None,
    options: list[str] | None = None,
    constraints: list[str] | None = None,
    assumptions: list[str] | None = None,
    status: str | None = None,
) -> DecisionCase:
    changes: dict[str, object] = {}
    if goal is not None:
        _refuse_if_briefed(case, "goal")
        changes["objective"] = goal.strip()
    if question is not None:
        _refuse_if_briefed(case, "question")
        asked = clean_question(question)
        changes["request"] = asked
        changes["decision"] = asked
    if context is not None:
        changes["context"] = context.strip()
    if owner is not None:
        changes["owner"] = owner.strip()
    if assumptions is not None:
        changes["assumptions"] = _lines(assumptions)
    if options is not None:
        _refuse_if_briefed(case, "options")
        changes["options"] = parse_options(options, case.options)
    if constraints is not None:
        _refuse_if_briefed(case, "constraints")
        changes["constraints"] = parse_constraints(constraints, case.constraints)
    if status is not None:
        stage = _status(status)
        if stage != case.status and stage not in OPEN_STATUSES:
            raise DecisionError("That status is set by the decision loop, not the registry.")
        changes["status"] = stage
    if not changes:
        raise DecisionError("Name a field to update.")
    return case.model_copy(update=changes)


def render_registry(case: DecisionCase) -> str:
    fields = [
        ("Goal", [_text(case.objective)]),
        ("Question", [_text(case.request)]),
        ("Context", [_text(case.context)]),
        ("Options", _options(case)),
        ("Constraints", _constraints(case)),
        ("Assumptions", _assumptions(case)),
        ("Evidence", _evidence(case)),
        ("Risks", _risks(case)),
        ("Recommendation", [_recommendation(case)]),
        ("Confidence", [_text(case.brief.confidence if case.brief else "")]),
        ("Owner", [_text(case.owner)]),
        ("Status", [case.status.value]),
        ("Outcome", _outcome(case)),
    ]
    title = case.decision.strip() or "Decision"
    lines = [title]
    last = len(fields) - 1
    for index, (name, values) in enumerate(fields):
        branch = "└──" if index == last else "├──"
        pad = "    " if index == last else "│   "
        lines.append(f"{branch} {name}")
        for value in values:
            lines.append(f"{pad}{value}")
    return "\n".join(lines) + "\n"


def parse_options(lines: list[str], existing: list[Option] | None = None) -> list[Option]:
    kept = {item.name: item for item in existing or []}
    options: list[Option] = []
    used: set[str] = set()
    for raw in lines:
        text = re.sub(r"^[A-Z]\.\s+", "", raw.strip())
        if not text:
            continue
        if " — " in text:
            name, summary = text.split(" — ", 1)
        elif " - " in text:
            name, summary = text.split(" - ", 1)
        else:
            name, summary = text, ""
        name = name.strip()
        if name in kept:
            options.append(kept[name])
            used.add(kept[name].key)
            continue
        key = _letter(used)
        used.add(key)
        options.append(Option(key=key, name=name, summary=summary.strip() or name))
    return options


def parse_constraints(lines: list[str], existing: list[Constraint] | None = None) -> list[Constraint]:
    kept = {item.statement: item for item in existing or []}
    items: list[Constraint] = []
    used: set[str] = set()
    for raw in lines:
        statement = re.sub(r"^-\s+", "", raw.strip())
        if not statement:
            continue
        if statement in kept:
            items.append(kept[statement])
            used.add(kept[statement].id)
            continue
        base = slug(statement)[:48] or "constraint"
        ident = base
        number = 2
        while ident in used:
            ident = f"{base}-{number}"
            number += 1
        used.add(ident)
        items.append(Constraint(id=ident, statement=statement, kind="stated"))
    return items


def _refuse_if_briefed(case: DecisionCase, field: str) -> None:
    if case.brief is not None or case.scenarios:
        raise DecisionError(f"The {field} is already part of a brief. The registry will not replace it.")


def _status(value: str) -> Stage:
    try:
        return Stage(value)
    except ValueError as exc:
        raise DecisionError(f"Unknown status {value}.") from exc


def _lines(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


def _text(value: str) -> str:
    return value.strip() or _BLANK


def _options(case: DecisionCase) -> list[str]:
    if not case.options:
        return [_BLANK]
    return [f"{item.key}. {item.name}" for item in case.options]


def _constraints(case: DecisionCase) -> list[str]:
    if not case.constraints:
        return [_BLANK]
    return [item.statement for item in case.constraints]


def _assumptions(case: DecisionCase) -> list[str]:
    if not case.assumptions:
        return [_BLANK]
    return list(case.assumptions)


def _evidence(case: DecisionCase) -> list[str]:
    if not case.evidence:
        return [_BLANK]
    return [item.statement for item in case.evidence]


def _risks(case: DecisionCase) -> list[str]:
    if not case.risks:
        return [_BLANK]
    return [f"{item.title} — {item.likelihood} probability, {item.impact} impact" for item in case.risks]


def _recommendation(case: DecisionCase) -> str:
    if case.brief is None or not case.brief.recommendation_key:
        return _BLANK
    option = case.option(case.brief.recommendation_key)
    if option is None:
        return case.brief.recommendation_key
    return f"{option.key}. {option.name}"


def _outcome(case: DecisionCase) -> list[str]:
    if not case.outcomes:
        return [_BLANK]
    lines: list[str] = []
    for outcome in case.outcomes:
        metric = case.metric(outcome.metric_id)
        if metric is None:
            continue
        lines.append(
            f"{metric.name}: predicted {format_amount(metric, outcome.predicted)}, "
            f"actual {format_amount(metric, outcome.actual)}, variance {outcome.variance}."
        )
    return lines or [_BLANK]


def _letter(used: set[str]) -> str:
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter not in used:
            return letter
    return "Z"
