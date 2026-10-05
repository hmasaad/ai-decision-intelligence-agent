"""What a decision changes before it is executed.

The map is read from the record. A decision affects the service and the
metrics it moves, depends on the assumptions that drive it, and conflicts
with another stored decision only when both are about the same service and
they choose different options.
"""

from decision.assumptions import driving
from decision.evidence import confidence_band
from decision.execute import execution_plan
from decision.learn import executed_option
from decision.models import DecisionCase, MetricSpec, Option, Reevaluation, Risk
from decision.text import format_amount, plain
from decision.uncertainty import return_confidence


class Link:
    def __init__(self, relation: str, target: str) -> None:
        self.relation = relation
        self.target = target


class _Node:
    def __init__(self, label: str, detail: str = "", children: list["_Node"] | None = None) -> None:
        self.label = label
        self.detail = detail
        self.children = children or []


def build_links(case: DecisionCase, others: list[DecisionCase] | None = None) -> list[Link]:
    """affects, depends_on, and conflicts_with, from the stored record."""

    chosen = executed_option(case)
    if chosen is None:
        return []
    links = [Link("affects", item) for item in _affected_names(case, chosen)]
    for item in driving(case):
        links.append(Link("depends_on", item.statement))
    for other, option in _conflicts(case, chosen, others or []):
        label = f"{other.id} ({option.key}. {option.name})" if option is not None else other.id
        links.append(Link("conflicts_with", label))
    return links


def render_impact(case: DecisionCase, others: list[DecisionCase] | None = None) -> str:
    """The dependency map, then direct and indirect impact."""

    report = _report(case, others or [])
    if report is None:
        return "Nothing is recommended yet, so the impact is not mapped.\n"
    parts = [
        report["tree"],
        "",
        report["links"],
        "",
        report["score"],
        "",
        report["propagation"],
        "",
        report["trigger"],
        "",
    ]
    for title, points in report["sections"]:
        parts.append(title)
        parts.extend(f"• {point}" for point in points)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def changes(case: DecisionCase | None, others: list[DecisionCase], asked: str) -> str:
    """If we make this decision, what else changes?"""

    if case is None:
        return "No stored decision is available to trace.\n"
    report = _report(case, others)
    if report is None:
        return "Nothing is recommended yet, so nothing else can be traced.\n"
    lines = [asked, "", case.decision or "Decision", "", report["lead"], ""]
    for title in ("Direct impacts", "Indirect impacts", "Dependencies"):
        points = _section(report, title)
        lines.append(title)
        lines.extend(f"• {point}" for point in points)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def invalidates(case: DecisionCase | None, others: list[DecisionCase], asked: str) -> str:
    """Which goals, plans, assumptions, and decisions this choice could invalidate."""

    if case is None:
        return "No stored decision is available to trace.\n"
    chosen = executed_option(case)
    if chosen is None:
        return "Nothing is recommended yet, so nothing else can be traced.\n"
    lines = [
        asked,
        "",
        case.decision or "Decision",
        "",
        f"{chosen.key}. {chosen.name} is the decision about to be executed.",
        "",
        "Goals",
    ]
    lines.extend(f"• {item}" for item in _goals(case, chosen))
    lines.extend(["", "Plans"])
    lines.extend(f"• {item}" for item in _plans(case, chosen, others))
    lines.extend(["", "Assumptions"])
    lines.extend(f"• {item}" for item in _assumption_breaks(case, chosen))
    lines.extend(["", "Decisions"])
    lines.extend(f"• {item}" for item in _decision_effects(case, chosen, others))
    return "\n".join(lines).rstrip() + "\n"


def page_view(case: DecisionCase, others: list[DecisionCase] | None = None) -> dict[str, object]:
    report = _report(case, others or [])
    if report is None:
        return {"ready": False, "empty": "Nothing is recommended yet, so the impact is not mapped.", "sections": []}
    sections = report["sections"]
    assert isinstance(sections, list)
    return {
        "ready": True,
        "empty": "",
        "tree": report["tree"],
        "links": report["links"],
        "score": report["score"],
        "propagation": report["propagation"],
        "trigger": report["trigger"],
        "sections": [{"title": title, "points": points} for title, points in sections],
    }


def attach_impact_trigger(case: DecisionCase) -> DecisionCase:
    """Open a re-evaluation when the executed option's impact breaks the record."""

    review = _impact_review(case)
    if review is None:
        return case
    return case.model_copy(update={"reevaluations": [*case.reevaluations, review]})


def render_trigger(case: DecisionCase, others: list[DecisionCase] | None = None) -> str:
    """Impact analysis, then whether that impact reopens the decision."""

    chosen = executed_option(case)
    if chosen is None:
        return "Decision Impact Analysis\nNothing is recommended yet, so no re-evaluation is triggered.\n"
    baseline = _baseline(case, chosen)
    scores = _scores(case, chosen, baseline)
    high = [_area_phrase(item.area) for item in scores if item.severity.word == "High"]
    overall = _highest(item.severity.word for item in scores) if scores else "Low"
    harms = _harms(case, chosen, others or [])
    steps = [
        ("Decision Impact Analysis", f"{chosen.key}. {chosen.name}. Overall impact is {overall}."),
        ("Significant impact detected", _significant_line(high)),
        ("Affected goal/plan identified", " ".join(_affected_lines(case, chosen))),
        ("Re-evaluation triggered", _triggered_line(case, high, harms)),
        ("Decision / plan updated", _updated_line(case, chosen)),
    ]
    lines: list[str] = []
    for index, (label, detail) in enumerate(steps):
        lines.append(label)
        lines.append(detail)
        if index < len(steps) - 1:
            lines.append("↓")
    return "\n".join(lines)


def answer(cases: list[DecisionCase], question: str, focus_id: str = "") -> str:
    asked = " ".join(question.split())
    if not asked:
        return "Ask what this decision would change.\n"
    if not cases:
        return "No decisions are stored, so nothing is affected yet.\n"
    focus = _focus(cases, focus_id)
    text = asked.lower()
    if "invalidat" in text:
        return invalidates(focus, cases, asked)
    return changes(focus, cases, asked)


def _report(case: DecisionCase, others: list[DecisionCase]) -> dict[str, object] | None:
    chosen = executed_option(case)
    if chosen is None:
        return None
    baseline = _baseline(case, chosen)
    groups = _groups(case, chosen, baseline)
    links = build_links(case, others)
    sections = [
        ("Direct impacts", _direct(case, chosen, baseline)),
        ("Indirect impacts", _indirect(case, chosen)),
        ("Dependencies", [item.statement for item in driving(case)] or ["No assumption is driving this decision."]),
        ("Risks", _risks(case, chosen)),
        ("Affected goals", _goals(case, chosen)),
        ("Affected decisions", _decision_effects(case, chosen, others)),
    ]
    return {
        "tree": _tree(case, groups),
        "links": _render_links(case, links),
        "lead": f"{chosen.key}. {chosen.name} is the decision about to be executed.",
        "sections": sections,
        "score": _render_scores(case, chosen, baseline),
        "propagation": _propagation(case, chosen, others),
        "trigger": render_trigger(case, others),
    }


class _Factor:
    def __init__(self, word: str, basis: str) -> None:
        self.word = word
        self.basis = basis


class _AreaScore:
    def __init__(self, area: str, severity: _Factor, probability: _Factor, scope: _Factor, reversibility: _Factor, confidence: _Factor) -> None:
        self.area = area
        self.severity = severity
        self.probability = probability
        self.scope = scope
        self.reversibility = reversibility
        self.confidence = confidence


def _render_scores(case: DecisionCase, chosen: Option, baseline: Option | None) -> str:
    scores = _scores(case, chosen, baseline)
    if not scores:
        return "Impact score\nNo affected area is scored yet."
    width = max(len(f"{item.area} impact:") for item in scores)
    width = max(width, len("Overall impact:"))
    lines = ["Impact score", chosen.name, ""]
    for item in scores:
        lines.append(f"{f'{item.area} impact:'.ljust(width)}  {item.severity.word}")
        for label, factor in (
            ("Severity", item.severity),
            ("Probability", item.probability),
            ("Scope", item.scope),
            ("Reversibility", item.reversibility),
            ("Confidence", item.confidence),
        ):
            lines.append(f"  {label.ljust(16)}{factor.word}. {factor.basis}")
        lines.append("")
    overall = _highest(item.severity.word for item in scores)
    lines.append(f"{'Overall impact:'.ljust(width)}  {overall}")
    lines.append("Overall impact is the highest severity.")
    return "\n".join(lines)


def _scores(case: DecisionCase, chosen: Option, baseline: Option | None) -> list[_AreaScore]:
    moves = _moves(case, chosen, baseline)
    by_area: dict[str, list[tuple[MetricSpec, float, float]]] = {}
    for metric, before, after in moves:
        if before == after:
            continue
        by_area.setdefault(_area(metric.id), []).append((metric, before, after))
    areas = ["Service"]
    for area in ("Engineering", "Operations", "Business"):
        if area in by_area:
            areas.append(area)
    if case.objective.strip():
        areas.append("Goal")
    undo = _reversibility(chosen)
    scored: list[_AreaScore] = []
    for area in areas:
        rows = by_area.get(area, [])
        if area == "Goal":
            rows = [(metric, before, after) for metric, before, after in moves if _named_in(metric.name, case.objective)]
        value, source = _confidence_source(case, chosen, area)
        scored.append(
            _AreaScore(
                area,
                _severity(case, chosen, area, rows),
                _probability(case, area, value, source),
                _scope(case, chosen, area, rows),
                undo,
                _confidence_factor(value, source),
            )
        )
    return scored


def _severity(case: DecisionCase, chosen: Option, area: str, rows: list[tuple[MetricSpec, float, float]]) -> _Factor:
    risk_word, risk_basis = _risk_word(case, area, "impact")
    share_word, share_basis = _share_word(rows)
    structural = _service_severity(chosen) if area == "Service" else None
    words = [item for item in (risk_word, share_word, structural[0] if structural else "") if item]
    if not words:
        return _Factor("Low", "No recorded move and no recorded risk.")
    word = _highest(words)
    basis = risk_basis if word == risk_word and risk_basis else ""
    if not basis and structural and word == structural[0]:
        basis = structural[1]
    if not basis:
        basis = share_basis
    return _Factor(word, basis or "Taken from the recorded move.")


def _probability(case: DecisionCase, area: str, value: float | None, source: str) -> _Factor:
    word, basis = _risk_word(case, area, "likelihood")
    if word:
        return _Factor(word, basis)
    if value is None:
        return _Factor("Low", "No estimate is on record for this area.")
    return _Factor(_band(value), f"{source}, {_percent(value)}.")


def _scope(case: DecisionCase, chosen: Option, area: str, rows: list[tuple[MetricSpec, float, float]]) -> _Factor:
    if area == "Service":
        if chosen.role == "replacement" or chosen.requires_downtime:
            return _Factor("High", "The option replaces the service or requires production downtime.")
        if _invoice(chosen):
            return _Factor("Medium", "The invoice pipeline moves. The service stays.")
        if chosen.role == "status_quo":
            return _Factor("Low", "The current service stays.")
        return _Factor("Medium", "The service changes.")
    if area == "Engineering":
        notes: list[str] = []
        headcount = _limit(case, "headcount")
        if chosen.engineers is not None and headcount is not None and chosen.engineers >= headcount:
            notes.append(f"Uses {plain(chosen.engineers)} of the {plain(headcount)} available engineers.")
        weeks = _limit(case, "timeline")
        if chosen.weeks is not None and weeks is not None and chosen.weeks >= weeks * 0.75:
            notes.append(f"Uses {plain(chosen.weeks)} of the {plain(weeks)} weeks.")
        if notes:
            return _Factor("High", " ".join(notes))
    word, basis = _share_word(rows)
    if word:
        return _Factor(word, basis)
    return _Factor("Low", "No recorded share of a constraint or a metric.")


def _reversibility(chosen: Option) -> _Factor:
    if not chosen.reversible:
        return _Factor("Low", "Not reversible.")
    if chosen.residual_risk:
        return _Factor("Medium", f"Reversible. {chosen.residual_risk}")
    return _Factor("High", "Reversible.")


def _confidence_factor(value: float | None, source: str) -> _Factor:
    if value is None:
        return _Factor("Low", "No confidence is on record.")
    return _Factor(_band(value), f"{source}, {_percent(value)}.")


def _propagation(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> str:
    lines = [
        "Decision",
        case.decision or "Not stated.",
        "↓",
        "Goal affected?",
        *_goals(case, chosen),
        "↓",
        "Subgoal affected?",
        *_subgoals(case, chosen),
        "↓",
        "Plan affected?",
        *_plan_lines(case, chosen),
        "↓",
        "Agent action required?",
        _action(case, chosen, others),
    ]
    return "\n".join(lines)


def _subgoals(case: DecisionCase, chosen: Option) -> list[str]:
    objective = case.objective.strip()
    if not objective:
        return ["No goal is recorded, so no subgoal is affected."]
    baseline = _baseline(case, chosen)
    lines: list[str] = []
    for metric, before, after in _moves(case, chosen, baseline):
        if not _named_in(metric.name, objective) or before == after:
            continue
        line = f"{metric.name} moves from {format_amount(metric, before)} to {format_amount(metric, after)}."
        if metric.id == "infra_cost":
            expected = case.scenario(chosen.key, "expected")
            if expected is not None and expected.headline:
                line += f" The annual change is {expected.headline}."
        lines.append(line)
    return lines or ["No metric named by the goal moves."]


def _plan_lines(case: DecisionCase, chosen: Option) -> list[str]:
    lines = [f"{step.name} {step.window}." if step.window else step.name for step in execution_plan(case, chosen)]
    worst = case.scenario(chosen.key, "pessimistic")
    if worst is not None and not worst.feasible and "timeline" in worst.block_codes and worst.blocked_by:
        detail = " ".join(worst.blocked_by)
        lines.append(f"The worst case {detail[:1].lower()}{detail[1:]}")
    if not case.execution:
        lines.append("The plan has not started.")
    elif all(step.status == "done" for step in case.execution):
        lines.append("The plan is complete.")
    else:
        pending = next(step for step in case.execution if step.status != "done")
        lines.append(f"The plan is running. The next step is {pending.name}")
    return lines


def _action(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> str:
    broken = _broken_phrase(case, chosen)
    if broken and case.status.value in {"executing", "tracking", "learned"}:
        return (
            "Agent action required. The plan is running, and "
            f"{broken} A person confirms the exception or the plan stops."
        )
    if broken:
        return f"Agent action required. Do not start the plan. {broken}"
    conflict = _conflicts(case, chosen, others)
    if conflict:
        other, option = conflict[0]
        return (
            "Agent action required. "
            f"Resolve {other.id} before execution. It chooses {option.key}. {option.name} on the same service."
        )
    if case.status.value in {"executing", "tracking"}:
        return "The plan is running. No further agent action is required until a step finishes or a constraint breaks."
    return "Human approval required. The agent does not start the plan."


def _impact_review(case: DecisionCase) -> Reevaluation | None:
    chosen = executed_option(case)
    if chosen is None:
        return None
    if any(item.kind == "impact" for item in case.reevaluations):
        return None
    if case.reevaluations and case.reevaluations[-1].kind in {"evidence", "outcome"}:
        return None
    baseline = _baseline(case, chosen)
    high = [_area_phrase(item.area) for item in _scores(case, chosen, baseline) if item.severity.word == "High"]
    harms = _harms(case, chosen, [])
    if not high or not harms:
        return None
    recommended = ""
    if case.brief is not None and case.brief.recommendation_key:
        option = case.option(case.brief.recommendation_key)
        if option is not None:
            recommended = f"The agent recommended {option.key}. {option.name}. "
    choice = f"The person chose {chosen.key}. {chosen.name}."
    if case.brief is not None and chosen.key == case.brief.recommendation_key:
        choice = f"{chosen.key}. {chosen.name}. The recommendation stays."
        recommended = ""
    return Reevaluation(
        evidence_id="impact",
        statement=harms[0],
        assumption=harms[0],
        risk="Significant impact is high.",
        outcome=" ".join(_affected_lines(case, chosen)),
        confidence_before=case.brief.confidence if case.brief else "low",
        confidence_after=case.brief.confidence if case.brief else "low",
        kind="impact",
        trigger=(
            f"Significant impact detected. {_join(high)} {_are(high)} high. "
            f"{harms[0]} Re-evaluation recommended."
        ),
        recommendation=f"{recommended}{choice}".strip(),
    )


def _harms(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> list[str]:
    lines: list[str] = []
    for line in _goals(case, chosen):
        if "set back" in line:
            lines.append(line)
    broken = _broken_phrase(case, chosen)
    if broken:
        lines.append(broken)
    for other, option in _conflicts(case, chosen, others):
        picked = f"{option.key}. {option.name}" if option is not None else other.id
        lines.append(f"{other.id} chooses {picked} on the same service.")
    return lines


def _significant_line(high: list[str]) -> str:
    if not high:
        return "No area is high severity."
    return f"Yes. {_join(high)} {_are(high)} high."


def _are(items: list[str]) -> str:
    return "is" if len(items) == 1 else "are"


def _affected_lines(case: DecisionCase, chosen: Option) -> list[str]:
    lines = list(_goals(case, chosen))
    if case.execution:
        pending = next((step.name for step in case.execution if step.status != "done"), "")
        if pending:
            lines.append(f"The plan is running. The next step is {pending}")
        elif all(step.status == "done" for step in case.execution):
            lines.append("The plan is complete.")
        else:
            lines.append("The plan has started.")
    else:
        lines.append("The plan has not started.")
    worst = case.scenario(chosen.key, "pessimistic")
    if worst is not None and not worst.feasible and "timeline" in worst.block_codes and worst.blocked_by:
        detail = " ".join(worst.blocked_by)
        lines.append(f"The worst case {detail[:1].lower()}{detail[1:]}")
    broken = _broken_phrase(case, chosen)
    if broken:
        lines.append(broken)
    return lines


def _triggered_line(case: DecisionCase, high: list[str], harms: list[str]) -> str:
    if case.reevaluations:
        latest = case.reevaluations[-1]
        if latest.accepted_note:
            who = latest.accepted_by or "A person whose name was not recorded"
            return f"Accepted by {who}. Reasoning: {latest.accepted_note}."
        return latest.trigger or latest.statement
    if harms:
        return f"{harms[0]} Re-evaluation recommended."
    if high:
        return "No re-evaluation is triggered. The high impact is already in the brief."
    return "No re-evaluation is triggered."


def _updated_line(case: DecisionCase, chosen: Option) -> str:
    if case.reevaluations:
        latest = case.reevaluations[-1]
        recommendation = latest.recommendation or f"{chosen.key}. {chosen.name}."
        if latest.accepted_note:
            return f"{recommendation} The executed plan stays in place."
        if latest.kind == "outcome":
            return f"{recommendation} The execution plan already run stays in place."
        if latest.kind == "impact":
            return f"{recommendation} The plan waits until a person confirms this impact."
        return f"{recommendation} The plan is not replaced until a person reviews this update."
    started = "The plan has started." if case.execution else "The plan has not started."
    return f"{chosen.key}. {chosen.name}. The recommendation stays. {started}"


def _area_phrase(area: str) -> str:
    if area == "Goal":
        return "the goal"
    return area


def _broken_phrase(case: DecisionCase, chosen: Option) -> str:
    broken = _broken_statements(case, chosen)
    if not broken:
        return ""
    return f"{chosen.key}. {chosen.name} would break these assumptions: {_join([_phrase(item) for item in broken])}."


def _broken_statements(case: DecisionCase, chosen: Option) -> list[str]:
    broken: list[str] = []
    for item in driving(case):
        if item.kind == "headcount" and chosen.engineers is not None:
            limit = _limit(case, "headcount")
            if limit is not None and chosen.engineers > limit:
                broken.append(item.statement)
        elif item.kind == "timeline" and chosen.weeks is not None:
            limit = _limit(case, "timeline")
            if limit is not None and chosen.weeks > limit:
                broken.append(item.statement)
        elif item.kind == "downtime" and chosen.requires_downtime and _limit(case, "downtime") == 0:
            broken.append(item.statement)
    return broken


def _assumption_breaks(case: DecisionCase, chosen: Option) -> list[str]:
    broken = _broken_statements(case, chosen)
    lines: list[str] = []
    if broken:
        lines.append(_broken_phrase(case, chosen))
    else:
        lines.append(f"{chosen.key}. {chosen.name} breaks none of the assumptions it depends on.")
    worst = case.scenario(chosen.key, "pessimistic")
    if worst is not None and not worst.feasible and "timeline" in worst.block_codes and worst.blocked_by:
        detail = " ".join(worst.blocked_by)
        lines.append(f"The worst case {detail[:1].lower()}{detail[1:]} That case would break the timeline.")
    return lines


def _affected_names(case: DecisionCase, chosen: Option) -> list[str]:
    names = [_service_name(case)]
    if _invoice(chosen):
        names.append("Invoice pipeline")
    baseline = _baseline(case, chosen)
    for metric, before, after in _moves(case, chosen, baseline):
        if before != after:
            names.append(metric.name)
    if case.objective.strip():
        names.append(case.objective.strip())
    return names


def _groups(case: DecisionCase, chosen: Option, baseline: Option | None) -> list[_Node]:
    groups: list[_Node] = []
    service_children = [_Node(_service_name(case), _service_detail(chosen))]
    if _invoice(chosen):
        service_children.append(_Node("Invoice pipeline", "This is the path the recommendation moves."))
    groups.append(_Node("Service", children=service_children))

    grouped: dict[str, list[_Node]] = {}
    for metric, before, after in _moves(case, chosen, baseline):
        if before == after:
            continue
        area = _area(metric.id)
        detail = f"{format_amount(metric, before)} → {format_amount(metric, after)}"
        if metric.id == "infra_cost":
            expected = case.scenario(chosen.key, "expected")
            if expected is not None and expected.headline:
                detail += f". The annual change is {expected.headline}"
        if metric.id == "effort" and chosen.engineers is not None:
            limit = _limit(case, "headcount")
            if limit is not None:
                detail += f". Uses {plain(chosen.engineers)} of the {plain(limit)} available engineers"
        grouped.setdefault(area, []).append(_Node(metric.name, detail))
    for area in ("Engineering", "Operations", "Business"):
        children = grouped.get(area)
        if children:
            groups.append(_Node(area, children=children))
    if case.objective.strip():
        groups.append(_Node("Goal", children=[_Node(case.objective.strip())]))
    return groups


def _direct(case: DecisionCase, chosen: Option, baseline: Option | None) -> list[str]:
    lines = [_service_detail(chosen)]
    moved = False
    for metric, before, after in _moves(case, chosen, baseline):
        if before == after:
            continue
        moved = True
        line = f"{metric.name} moves from {format_amount(metric, before)} to {format_amount(metric, after)}."
        if metric.id == "infra_cost":
            expected = case.scenario(chosen.key, "expected")
            if expected is not None and expected.headline:
                line += f" The annual change is {expected.headline}."
        if metric.id == "effort" and chosen.engineers is not None:
            limit = _limit(case, "headcount")
            available = f" of the {plain(limit)} available" if limit is not None else ""
            line += f" It uses {plain(chosen.engineers)}{available} engineers."
        lines.append(line)
    if not moved:
        lines.append("The recorded metrics do not move.")
    return lines


def _indirect(case: DecisionCase, chosen: Option) -> list[str]:
    lines: list[str] = []
    limit = _limit(case, "headcount")
    if limit is not None and chosen.engineers is not None and chosen.engineers >= limit:
        blocked = [
            f"{option.name} needs {plain(option.engineers)}"
            for option in case.options
            if option.engineers is not None and option.engineers > limit
        ]
        if blocked:
            joined = _join(blocked)
            lines.append(
                f"{chosen.name} uses all {plain(limit)} available engineers. {joined} and stays blocked."
            )
    if chosen.residual_risk:
        lines.append(chosen.residual_risk)
    for item in case.evidence:
        if "invoice delay" in item.statement.lower():
            lines.append(f"{item.statement} No separate measure of those delays is on record.")
            break
    return lines or ["No indirect change is on record."]


def _risks(case: DecisionCase, chosen: Option) -> list[str]:
    lines = []
    for risk in case.risks:
        detail = f" {risk.detail}" if risk.detail else ""
        lines.append(f"{risk.title}.{detail}")
    return lines or [f"No risk is recorded on {chosen.name}."]


def _goals(case: DecisionCase, chosen: Option) -> list[str]:
    objective = case.objective.strip()
    if not objective:
        return ["No goal is recorded on this decision."]
    baseline = _baseline(case, chosen)
    falls = []
    rises = []
    for metric, before, after in _moves(case, chosen, baseline):
        if before == after or not _named_in(metric.name, objective):
            continue
        if metric.direction == "lower" and after < before:
            falls.append(metric.name.lower())
        elif metric.direction == "lower" and after > before:
            rises.append(metric.name.lower())
    if falls and not rises:
        named = list(falls)
        named[0] = named[0][:1].upper() + named[0][1:]
        return [f"{objective} {_join(named)} fall, so this goal still holds."]
    if rises:
        return [f"{objective} {_join(rises)} move the wrong way, so this goal would be set back."]
    return [f"{objective} The expected case does not show this goal moving."]


def _plans(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> list[str]:
    lines: list[str] = []
    for other, option in _conflicts(case, chosen, others):
        if not other.execution:
            continue
        steps = _join([step.name for step in other.execution])
        lines.append(f"{other.id} has a plan: {steps}. Executing this decision conflicts with that plan.")
    if lines:
        return lines
    return ["No stored plan is invalidated."]


def _decision_effects(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> list[str]:
    lines: list[str] = []
    for other in others:
        if other.id == case.id or not _same_subject(case, other):
            continue
        option = executed_option(other)
        if option is None:
            lines.append(f"{other.id} is also about the {_service_name(case).lower()}. It has no recommendation yet.")
            continue
        if option.key != chosen.key:
            lines.append(
                f"{other.id} chooses {option.key}. {option.name} on the same service. "
                f"Executing {chosen.key}. {chosen.name} conflicts with it."
            )
        else:
            lines.append(f"{other.id} chooses the same option on the same service.")
    return lines or ["No other stored decision is affected."]


def _conflicts(case: DecisionCase, chosen: Option, others: list[DecisionCase]) -> list[tuple[DecisionCase, Option | None]]:
    found: list[tuple[DecisionCase, Option | None]] = []
    for other in others:
        if other.id == case.id or not _same_subject(case, other):
            continue
        option = executed_option(other)
        if option is not None and option.key != chosen.key:
            found.append((other, option))
    return found


def _moves(
    case: DecisionCase, chosen: Option, baseline: Option | None
) -> list[tuple[MetricSpec, float, float]]:
    rows: list[tuple[MetricSpec, float, float]] = []
    if baseline is None:
        return rows
    before = case.scenario(baseline.key, "expected")
    after = case.scenario(chosen.key, "expected")
    if before is None or after is None:
        return rows
    for metric in case.metrics:
        if metric.id not in before.values or metric.id not in after.values:
            continue
        rows.append((metric, before.values[metric.id], after.values[metric.id]))
    return rows


def _named_in(name: str, objective: str) -> bool:
    text = objective.lower()
    return any(word in text for word in name.lower().split() if len(word) > 3)


def _service_detail(chosen: Option) -> str:
    text = chosen.summary.strip()
    if text.lower().startswith("hybrid:"):
        text = text.split(":", 1)[1].strip()
        text = text[:1].upper() + text[1:]
    if text and not text.endswith("."):
        text += "."
    return text or "The service is what this decision changes."


def _invoice(chosen: Option) -> bool:
    return "invoice pipeline" in chosen.summary.lower()


def _service_name(case: DecisionCase) -> str:
    name = case.subject.strip()
    if not name:
        return "The service"
    pretty = name[:1].upper() + name[1:]
    if pretty.lower().endswith("service"):
        return pretty
    return f"{pretty} service"


def _risk_word(case: DecisionCase, area: str, field: str) -> tuple[str, str]:
    words: list[str] = []
    bases: list[str] = []
    for risk in case.risks:
        if _risk_area(risk) != area:
            continue
        raw = risk.impact if field == "impact" else risk.likelihood
        words.append(_band_word(raw))
        bases.append(f"Recorded {field} is {raw}: {risk.title}.")
    if not words:
        return "", ""
    word = _highest(words)
    basis = next(item for item, rank in zip(bases, words) if rank == word)
    return word, basis


def _risk_area(risk: Risk) -> str:
    title = risk.title.lower()
    if "capacity" in title or "delay" in title:
        return "Engineering"
    if "regression" in title or "incident" in title:
        return "Operations"
    if "cost" in title:
        return "Business"
    return ""


def _share_word(rows: list[tuple[MetricSpec, float, float]]) -> tuple[str, str]:
    best = 0.0
    metric: MetricSpec | None = None
    for item, before, after in rows:
        share = _share(before, after)
        if share >= best:
            best = share
            metric = item
    if metric is None:
        return "", ""
    percent = round(best * 100)
    return _from_share(best), f"{metric.name} moves by {percent}%."


def _share(before: float, after: float) -> float:
    base = abs(before) if abs(before) > 1e-9 else abs(after)
    if base < 1e-9:
        return 0.0
    return abs(after - before) / base


def _from_share(share: float) -> str:
    if share >= 0.5:
        return "High"
    if share >= 0.2:
        return "Medium"
    return "Low"


def _service_severity(chosen: Option) -> tuple[str, str]:
    if chosen.role == "replacement" or chosen.requires_downtime:
        return "High", "The option replaces the service or requires production downtime."
    if chosen.role == "status_quo":
        return "Low", "The current service stays."
    return "Medium", "A path inside the service moves."


def _confidence_source(case: DecisionCase, chosen: Option, area: str) -> tuple[float | None, str]:
    if area in {"Business", "Goal"}:
        return return_confidence(case, chosen.key), "Expected return"
    if area in {"Service", "Operations"}:
        experiments = [item for item in case.evidence if item.option_key == chosen.key and item.kind == "experiment"]
        if experiments:
            item = min(experiments, key=lambda claim: claim.confidence)
            return item.confidence, item.source
    estimates = [item for item in case.evidence if item.option_key == chosen.key and item.kind == "estimate"]
    if estimates:
        item = min(estimates, key=lambda claim: claim.confidence)
        return item.confidence, item.source
    return return_confidence(case, chosen.key), "Expected return"


def _band(value: float) -> str:
    return _band_word(confidence_band(value))


def _band_word(value: str) -> str:
    text = value.strip().lower()
    if text == "high":
        return "High"
    if text == "medium":
        return "Medium"
    return "Low"


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _highest(words) -> str:
    order = {"Low": 1, "Medium": 2, "High": 3}
    return max(words, key=lambda word: order.get(word, 0))


def _area(metric_id: str) -> str:
    if metric_id in {"deploy_time", "effort"}:
        return "Engineering"
    if metric_id == "incident_rate":
        return "Operations"
    if metric_id == "infra_cost":
        return "Business"
    return "Recorded"


def _tree(case: DecisionCase, groups: list[_Node]) -> str:
    lines = ["Decision", case.decision or "Not stated.", "│"]
    lines.extend(_branches(groups, ""))
    return "\n".join(lines)


def _branches(nodes: list[_Node], indent: str) -> list[str]:
    lines: list[str] = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        lines.append(f"{indent}{'└── ' if last else '├── '}{node.label}")
        nest = indent + ("    " if last else "│   ")
        if node.detail:
            lines.append(f"{nest}{node.detail}")
        lines.extend(_branches(node.children, nest))
    return lines


def _render_links(case: DecisionCase, links: list[Link]) -> str:
    if not links:
        return f"{case.id}\n  No relationship is on record."
    lines = [case.id]
    for link in links:
        lines.append(f"  {link.relation} → {link.target}")
    return "\n".join(lines)


def _section(report: dict[str, object], title: str) -> list[str]:
    sections = report["sections"]
    assert isinstance(sections, list)
    for name, points in sections:
        if name == title:
            return points
    return []


def _baseline(case: DecisionCase, chosen: Option) -> Option | None:
    for option in case.options:
        if option.role == "status_quo":
            return option
    for option in case.options:
        if option.key != chosen.key:
            return option
    return None


def _same_subject(left: DecisionCase, right: DecisionCase) -> bool:
    subject = left.subject.strip().lower()
    return bool(subject) and subject == right.subject.strip().lower()


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _focus(cases: list[DecisionCase], focus_id: str) -> DecisionCase | None:
    if focus_id:
        for case in cases:
            if case.id == focus_id:
                return case
        return None
    briefed = [case for case in cases if case.brief and case.brief.recommendation_key]
    if len(briefed) == 1:
        return briefed[0]
    return briefed[-1] if briefed else cases[-1]


def _phrase(statement: str) -> str:
    text = statement.rstrip(".")
    if text.startswith("The "):
        return "the " + text[4:]
    if text[:1].isupper():
        return text[:1].lower() + text[1:]
    return text


def _join(items: list[str]) -> str:
    names = [item for item in items if item]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
