"""A decision as a causal graph, read from the record.

Evidence supports an assumption. The assumption grounds a constraint. The
constraint admits one option and blocks another. That option carries an
expected outcome, the risks on it, and the decision a person is asked to
make. After the work ships, the actual outcome revises what was learned.

The graph answers from those links. It does not invent a path the case
does not contain.
"""

import re

from decision.models import Constraint, DecisionCase, Evidence, Option
from decision.text import format_amount, plain
from decision.whatif import WhatIf, answer, opening, render_whatif

CHAIN = (
    ("evidence", "Evidence"),
    ("assumption", "Assumption"),
    ("constraint", "Constraint"),
    ("option", "Option"),
    ("outcome", "Expected outcome"),
    ("risk", "Risk"),
    ("decision", "Decision"),
    ("actual", "Actual outcome"),
    ("learning", "Learning"),
)

_SKIPPED_KINDS = {"estimate", "precedent", "experiment", "market"}


class Node:
    def __init__(self, id: str, kind: str, label: str, detail: str = "") -> None:
        self.id = id
        self.kind = kind
        self.label = label
        self.detail = detail


class Edge:
    def __init__(self, source: str, target: str, relation: str) -> None:
        self.source = source
        self.target = target
        self.relation = relation


class Graph:
    def __init__(self, nodes: list[Node], edges: list[Edge]) -> None:
        self.nodes = nodes
        self.edges = edges

    def node(self, node_id: str) -> Node | None:
        for item in self.nodes:
            if item.id == node_id:
                return item
        return None

    def layers(self) -> list[dict[str, object]]:
        grouped: list[dict[str, object]] = []
        for kind, title in CHAIN:
            items = [item for item in self.nodes if item.kind == kind]
            if not items:
                items = [Node(f"empty-{kind}", kind, "Not on record yet.")]
            grouped.append(
                {
                    "kind": kind,
                    "title": title,
                    "nodes": [{"label": item.label, "detail": item.detail} for item in items],
                }
            )
        return grouped


def build_graph(case: DecisionCase) -> Graph:
    """The causal chain for one stored decision."""

    nodes: list[Node] = []
    edges: list[Edge] = []
    chosen_key = case.brief.recommendation_key if case.brief else None
    chosen = case.option(chosen_key) if chosen_key else None
    chosen_expected = case.scenario(chosen_key, "expected") if chosen_key else None
    held_back = _higher_blocked(case, chosen_expected)
    visible = {item.key for item, _expected in held_back}
    if chosen is not None:
        visible.add(chosen.key)
    elif not visible:
        visible = {item.key for item in case.options}

    for constraint in case.constraints:
        assumption_id = f"assumption:{constraint.kind}"
        nodes.append(Node(assumption_id, "assumption", constraint.statement, _assumption_detail(case, constraint)))
        nodes.append(Node(f"constraint:{constraint.kind}", "constraint", constraint.statement, _constraint_detail(case, constraint, chosen)))
        edges.append(Edge(assumption_id, f"constraint:{constraint.kind}", "grounds"))
        for evidence in _constraint_evidence(case, constraint):
            evidence_id = f"evidence:{evidence.id}"
            if all(item.id != evidence_id for item in nodes):
                nodes.append(Node(evidence_id, "evidence", evidence.source, ""))
            relation = "challenges" if evidence.challenges == constraint.kind else "supports"
            edges.append(Edge(evidence_id, assumption_id, relation))

    for option in case.options:
        if option.key not in visible:
            continue
        expected = case.scenario(option.key, "expected")
        blocked = bool(expected and expected.blocked_by)
        if expected is None:
            detail = "Recorded. Not scored yet."
        elif option.key == chosen_key:
            detail = "Admitted. This is the option the constraints leave open."
        elif blocked:
            detail = " ".join(expected.blocked_by)
        else:
            detail = "Admitted by the constraints that the higher-scoring option misses."
        nodes.append(Node(f"option:{option.key}", "option", f"{option.key}. {option.name}", detail))
        for constraint in case.constraints:
            if expected is None:
                continue
            relation = "blocks" if constraint.kind in expected.block_codes else "admits"
            if relation == "admits" and option.key != chosen_key:
                continue
            edges.append(Edge(f"constraint:{constraint.kind}", f"option:{option.key}", relation))
        if expected is None:
            continue
        outcome_id = f"outcome:{option.key}"
        headline = expected.headline or "No infrastructure estimate."
        nodes.append(
            Node(outcome_id, "outcome", f"Expected outcome of {option.name}", headline)
        )
        edges.append(Edge(f"option:{option.key}", outcome_id, "expects"))
        for evidence in case.evidence:
            if evidence.option_key != option.key:
                continue
            evidence_id = f"evidence:{evidence.id}"
            if all(item.id != evidence_id for item in nodes):
                nodes.append(Node(evidence_id, "evidence", evidence.source, ""))
            edges.append(Edge(evidence_id, outcome_id, "supports"))

    outcome_anchor = f"outcome:{chosen_key}" if chosen_key else ""
    for index, risk in enumerate(case.risks):
        risk_id = f"risk:{index}"
        nodes.append(
            Node(
                risk_id,
                "risk",
                risk.title,
                f"{risk.likelihood} probability, {risk.impact} impact, residual {risk.residual}.",
            )
        )
        if outcome_anchor and any(item.id == outcome_anchor for item in nodes):
            edges.append(Edge(outcome_anchor, risk_id, "exposes"))

    decision_detail = "Not recommended yet."
    if chosen is not None:
        decision_detail = f"Recommends {chosen.key}. {chosen.name}."
        if case.review_action == "approved":
            who = case.approved_by or "a person whose name was not recorded"
            decision_detail += f" Approved by {who}."
    nodes.append(Node("decision", "decision", case.decision or "Not stated.", decision_detail))
    if case.risks:
        edges.append(Edge(f"risk:{len(case.risks) - 1}", "decision", "informs"))
    elif outcome_anchor and any(item.id == outcome_anchor for item in nodes):
        edges.append(Edge(outcome_anchor, "decision", "selects"))

    if case.outcomes:
        for outcome in case.outcomes:
            metric = case.metric(outcome.metric_id)
            if metric is None:
                continue
            actual_id = f"actual:{outcome.metric_id}"
            nodes.append(
                Node(
                    actual_id,
                    "actual",
                    metric.name,
                    (
                        f"Predicted {format_amount(metric, outcome.predicted)}. "
                        f"Actual {format_amount(metric, outcome.actual)}. "
                        f"Variance {outcome.variance}."
                    ),
                )
            )
            edges.append(Edge("decision", actual_id, "records"))
    else:
        nodes.append(Node("actual:empty", "actual", "Not recorded yet."))

    if case.lesson is not None:
        nodes.append(Node("learning", "learning", case.lesson.reason))
        if case.outcomes:
            edges.append(Edge(f"actual:{case.outcomes[-1].metric_id}", "learning", "revises"))
    else:
        nodes.append(Node("learning:empty", "learning", "Not written yet."))

    _fill_evidence_details(nodes, edges)
    return Graph(nodes, edges)


def render_graph(case: DecisionCase) -> str:
    lines: list[str] = []
    for layer in build_graph(case).layers():
        lines.append(str(layer["title"]).upper())
        nodes = layer["nodes"]
        assert isinstance(nodes, list)
        for node in nodes:
            lines.append(f"• {node['label']}")
            if node["detail"]:
                lines.append(f"  {node['detail']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def ask(cases: list[DecisionCase], question: str, focus_id: str = "") -> str:
    """Answer one of the four graph questions from stored decisions."""

    asked = " ".join(question.split())
    if not asked:
        return "Ask the graph a question.\n"
    if not cases:
        return "No decisions are stored, so the graph is empty.\n"
    text = asked.lower()
    focus = _focus(cases, focus_id)
    if _is_why(text):
        from decision.reason import why

        return why(focus, asked)
    if "assumption" in text and "driving" in text:
        from decision.assumptions import answer as driving_answer

        return driving_answer(focus, asked)
    if _is_responsible(text):
        return _responsible_answer(focus, asked)
    if _is_invalidate(text):
        return _invalidate_answer(focus, asked)
    if _is_depend(text):
        return _depend_answer(cases, asked, focus)
    if "what happens" in text and "assumption" in text and "constraint" not in text:
        from decision.scenarios import answer as scenario_answer

        return scenario_answer(focus, asked)
    if _is_change(text):
        return _change_answer(focus, asked)
    return (
        "The graph can say why a recommendation was reached, "
        "which assumptions are responsible for a decision, "
        "what evidence would invalidate it, which decisions depend on an assumption, "
        "and what happens if a constraint changes.\n"
    )


def responsible_constraints(case: DecisionCase) -> list[Constraint]:
    """Constraints that block an option scoring above the recommendation."""

    chosen = case.scenario(case.brief.recommendation_key, "expected") if case.brief and case.brief.recommendation_key else None
    if chosen is None:
        return []
    kinds: set[str] = set()
    for _option, expected in _higher_blocked(case, chosen):
        kinds.update(expected.block_codes)
    return [item for item in case.constraints if item.kind in kinds]


def _responsible_answer(case: DecisionCase | None, asked: str) -> str:
    if case is None:
        return "No stored decision is available to trace.\n"
    if case.brief is None or not case.brief.recommendation_key:
        return "Nothing is recommended yet, so no assumption is responsible for a choice.\n"
    chosen = case.option(case.brief.recommendation_key)
    constraints = responsible_constraints(case)
    if chosen is None or not constraints:
        return "No assumption on record is blocking a higher-scoring option.\n"
    lines = [
        asked,
        "",
        case.decision,
        (
            f"{chosen.name} is the recommendation. "
            "These assumptions are responsible because each one blocks a higher-scoring option."
        ),
        "",
    ]
    for constraint in constraints:
        lines.append(f"• {constraint.statement}")
        lines.append(f"  {_assumption_detail(case, constraint)}")
        blocked = _blocked_by(case, constraint.kind, chosen)
        if blocked:
            lines.append(f"  Blocks {blocked}.")
    return "\n".join(lines) + "\n"


def _invalidate_answer(case: DecisionCase | None, asked: str) -> str:
    if case is None:
        return "No stored decision is available to trace.\n"
    if case.brief is None or not case.brief.recommendation_key:
        return "Nothing is recommended yet, so there is no decision to invalidate.\n"
    chosen_option = case.option(case.brief.recommendation_key)
    chosen = case.scenario(case.brief.recommendation_key, "expected")
    if chosen_option is None or chosen is None:
        return "Nothing is recommended yet, so there is no decision to invalidate.\n"
    held = _higher_blocked(case, chosen)
    if not held:
        return "No higher-scoring option is blocked, so no constraint evidence would change the call.\n"
    lines = [
        asked,
        "",
        case.decision,
        f"{chosen_option.name} is the recommendation.",
        "",
    ]
    for constraint in responsible_constraints(case):
        if _constraint_evidence(case, constraint):
            continue
        lines.append(
            f"The assumption “{constraint.statement}” has no evidence behind it. "
            "A recorded change to that limit is what would replace it."
        )
        lines.append("")
    for option, expected in held:
        codes = list(dict.fromkeys(expected.block_codes))
        names = [_constraint_name(case, code) for code in codes]
        lifts = [_lift(case, code, option) for code in codes]
        joined = _join(names)
        lines.append(f"{option.name} scores higher and is blocked by {joined}.")
        if len(lifts) == 1:
            lines.append(f"The evidence that would invalidate the decision is {lifts[0]}.")
        else:
            lines.append("The evidence that would invalidate the decision is all of the following together:")
            lines.extend(f"• {item}" for item in lifts)
            lines.append(f"One of them leaves {option.name} blocked, so the recommendation would stay.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _depend_answer(cases: list[DecisionCase], asked: str, focus: DecisionCase | None) -> str:
    kind = _assumption_kind(asked)
    if not kind and focus is not None and "this assumption" in asked.lower():
        kinds = [item.kind for item in responsible_constraints(focus)]
        if len(kinds) == 1:
            kind = kinds[0]
    if not kind:
        return (
            "No stored decision depends on that assumption. "
            "The graph only answers from decisions recorded in this workspace.\n"
        )
    label = _kind_label(kind)
    found = [case for case in cases if any(item.kind == kind for item in responsible_constraints(case))]
    if not found:
        return (
            f"No stored decision depends on {label}. "
            "The graph only answers from decisions recorded in this workspace.\n"
        )
    lines = [asked, "", f"Decisions that depend on {label}:", ""]
    for case in found:
        chosen = case.option(case.brief.recommendation_key) if case.brief and case.brief.recommendation_key else None
        blocked = _blocked_by(case, kind, chosen) if chosen else ""
        because = f" {blocked} is blocked by it, so the recommendation depends on it." if blocked else ""
        lines.append(f"• {case.id} — {case.decision}{because}")
    return "\n".join(lines) + "\n"


def _change_answer(case: DecisionCase | None, asked: str) -> str:
    if case is None or not case.scenarios:
        return "That decision has no estimates, so a constraint change cannot be traced yet.\n"
    parsed = _parse_change(asked)
    if parsed is None:
        return "Ask what happens if a constraint changes.\n"
    if not parsed["specified"]:
        item = _opening_whatif(case)
        if item is None:
            return "No higher-scoring option is held back by a constraint.\n"
        lead = (
            "The constraints holding back a higher-scoring option are changed together. "
            "That is the constraint change this decision is sitting on.\n\n"
        )
        return lead + render_whatif(item)
    current_engineers = _limit(case, "headcount")
    current_weeks = _limit(case, "timeline")
    engineers = current_engineers if parsed["engineers"] is None else parsed["engineers"]
    weeks = current_weeks if parsed["weeks"] is None else parsed["weeks"]
    item = answer(
        case,
        engineers=engineers,
        from_engineers=current_engineers,
        weeks=weeks,
        from_weeks=current_weeks,
        downtime_forbidden=parsed["downtime"],
    )
    if item is None:
        return "That decision has no estimates, so a constraint change cannot be traced yet.\n"
    moved = _moved(parsed)
    lead = f"Only {moved} changes. The other constraints stay as recorded.\n\n"
    return lead + render_whatif(item)


def _assumption_detail(case: DecisionCase, constraint: Constraint) -> str:
    evidence = [item for item in _constraint_evidence(case, constraint) if item.challenges != constraint.kind]
    challenges = [item for item in _constraint_evidence(case, constraint) if item.challenges == constraint.kind]
    parts: list[str] = []
    if evidence:
        sources = _join([item.source for item in evidence])
        parts.append(f"Rests on {sources}.")
    else:
        parts.append("No evidence on record supports this assumption.")
    if challenges:
        parts.append(f"Challenged by {_join([item.source for item in challenges])}.")
    return " ".join(parts)


def _constraint_detail(case: DecisionCase, constraint: Constraint, chosen: Option | None) -> str:
    parts: list[str] = []
    if chosen is not None:
        expected = case.scenario(chosen.key, "expected")
        if expected is not None and constraint.kind not in expected.block_codes and expected.feasible:
            parts.append(f"Admits {chosen.name}.")
    blocked = _blocked_by(case, constraint.kind, chosen)
    if blocked:
        parts.append(f"Blocks {blocked}.")
    return " ".join(parts)


def _constraint_evidence(case: DecisionCase, constraint: Constraint) -> list[Evidence]:
    matched: list[Evidence] = []
    for item in case.evidence:
        if item.option_key:
            continue
        if item.challenges == constraint.kind:
            matched.append(item)
            continue
        if item.kind in _SKIPPED_KINDS:
            continue
        text = item.statement.lower()
        if constraint.kind == "headcount" and "engineer" in text:
            matched.append(item)
        elif constraint.kind == "downtime" and "downtime" in text:
            matched.append(item)
        elif constraint.kind == "timeline" and item.kind == "constraint" and "week" in text:
            matched.append(item)
    return matched


def _higher_blocked(case: DecisionCase, chosen):
    if chosen is None:
        return []
    held = []
    for option in case.options:
        expected = case.scenario(option.key, "expected")
        if expected is None or option.key == chosen.option_key or expected.feasible:
            continue
        if expected.score <= chosen.score + 0.01:
            continue
        held.append((option, expected))
    held.sort(key=lambda item: item[1].score, reverse=True)
    return held


def _blocked_by(case: DecisionCase, kind: str, chosen: Option | None) -> str:
    names: list[str] = []
    chosen_expected = case.scenario(chosen.key, "expected") if chosen else None
    for option, expected in _higher_blocked(case, chosen_expected):
        if kind in expected.block_codes:
            names.append(option.name)
    return _join(names)


def _lift(case: DecisionCase, kind: str, option: Option) -> str:
    expected = case.scenario(option.key, "expected")
    if kind == "headcount" and option.engineers is not None:
        noun = "engineer" if option.engineers == 1 else "engineers"
        return f"evidence that at least {plain(option.engineers)} {noun} are available"
    if kind == "timeline":
        weeks = expected.values.get("effort") if expected else None
        if weeks is None:
            weeks = option.weeks
        if weeks is not None:
            return f"evidence that the timeline is at least {plain(weeks)} weeks"
    if kind == "downtime":
        return "evidence that production downtime is allowed"
    statement = _constraint_name(case, kind)
    return f"evidence that changes {statement}"


def _constraint_name(case: DecisionCase, kind: str) -> str:
    for item in case.constraints:
        if item.kind == kind:
            return item.statement
    return kind


def _fill_evidence_details(nodes: list[Node], edges: list[Edge]) -> None:
    by_id = {item.id: item for item in nodes}
    for node in nodes:
        if node.kind != "evidence":
            continue
        parts: list[str] = []
        for edge in edges:
            if edge.source != node.id:
                continue
            target = by_id.get(edge.target)
            if target is None:
                continue
            verb = "Challenges" if edge.relation == "challenges" else "Supports"
            parts.append(f"{verb} {target.label}.")
        node.detail = " ".join(parts)


def _focus(cases: list[DecisionCase], focus_id: str) -> DecisionCase | None:
    if focus_id:
        for case in cases:
            if case.id == focus_id:
                return case
        return None
    if len(cases) == 1:
        return cases[0]
    briefed = [case for case in cases if case.brief and case.brief.recommendation_key]
    if len(briefed) == 1:
        return briefed[0]
    return briefed[-1] if briefed else (cases[-1] if cases else None)


def _is_why(text: str) -> bool:
    return "why" in text and ("recommend" in text or "reach" in text)


def _is_responsible(text: str) -> bool:
    return "assumption" in text and "responsible" in text


def _is_invalidate(text: str) -> bool:
    return "invalidat" in text


def _is_depend(text: str) -> bool:
    return "depend" in text


def _is_change(text: str) -> bool:
    return "what happens" in text and (
        "constraint" in text or "timeline" in text or "headcount" in text or "downtime" in text or "engineer" in text
    )


def _assumption_kind(question: str) -> str:
    text = question.lower()
    if "downtime" in text:
        return "downtime"
    if "timeline" in text or re.search(r"\bweeks?\b", text):
        return "timeline"
    if "headcount" in text or "engineer" in text or "capacity" in text:
        return "headcount"
    return ""


def _kind_label(kind: str) -> str:
    if kind == "downtime":
        return "no production downtime"
    if kind == "timeline":
        return "the timeline"
    if kind == "headcount":
        return "headcount"
    return kind


def _parse_change(question: str) -> dict[str, object] | None:
    text = question.lower()
    if not _is_change(text):
        return None
    engineers = _number_for(text, ("engineers", "engineer"), ("headcount",))
    weeks = _number_for(text, ("weeks", "week"), ("timeline",))
    downtime = None
    if re.search(r"downtime is allowed|allow downtime|downtime allowed", text):
        downtime = False
    elif re.search(r"forbid downtime|downtime is forbidden", text):
        downtime = True
    specified = engineers is not None or weeks is not None or downtime is not None
    return {"engineers": engineers, "weeks": weeks, "downtime": downtime, "specified": specified}


def _number_for(text: str, units: tuple[str, ...], aliases: tuple[str, ...]) -> float | None:
    unit = "|".join(units)
    match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{unit})", text)
    if match:
        return float(match.group(1))
    alias = "|".join(aliases)
    match = re.search(rf"(?:{alias})(?: constraint)?(?: changes)? to (\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    return None


def _moved(parsed: dict[str, object]) -> str:
    parts: list[str] = []
    if parsed["engineers"] is not None:
        parts.append("headcount")
    if parsed["weeks"] is not None:
        parts.append("the timeline")
    if parsed["downtime"] is not None:
        parts.append("the downtime rule")
    return _join(parts)


def _opening_whatif(case: DecisionCase) -> WhatIf | None:
    raw = opening(case)
    if not raw:
        return None
    params = dict(part.split("=", 1) for part in raw.split("&"))

    def num(key: str) -> float | None:
        return float(params[key]) if key in params else None

    return answer(
        case,
        engineers=num("engineers"),
        from_engineers=num("from_engineers"),
        weeks=num("weeks"),
        from_weeks=num("from_weeks"),
        downtime_forbidden=False if params.get("downtime") == "allow" else None,
    )


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _join(items: list[str]) -> str:
    names = [item for item in items if item]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
