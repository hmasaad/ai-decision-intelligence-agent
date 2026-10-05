"""The path from evidence to the recommendation.

Evidence supports an assumption. The assumption and the constraints admit
one option. That option carries an expected outcome, and the outcome is
what the recommendation rests on. The map is read from the record.
"""

from decision.assumptions import TrackedAssumption, driving
from decision.graph import responsible_constraints
from decision.models import Constraint, DecisionCase, Option, Scenario


class MapNode:
    def __init__(self, label: str, detail: str = "") -> None:
        self.label = label
        self.detail = detail


class ReasonMap:
    def __init__(
        self,
        evidence: list[MapNode],
        assumptions: list[MapNode],
        constraints: list[MapNode],
        option: MapNode | None,
        outcome: MapNode | None,
        decision: MapNode | None,
        because: str,
        empty: str,
    ) -> None:
        self.evidence = evidence
        self.assumptions = assumptions
        self.constraints = constraints
        self.option = option
        self.outcome = outcome
        self.decision = decision
        self.because = because
        self.empty = empty

    @property
    def ready(self) -> bool:
        return self.option is not None


def build_map(case: DecisionCase) -> ReasonMap:
    """The connected path that reaches the recommendation, or an empty map."""

    chosen = _chosen(case)
    drivers = driving(case)
    if chosen is None or not drivers:
        return ReasonMap([], [], [], None, None, None, "", _empty(case))

    evidence = [
        MapNode(line, _evidence_detail(line, item))
        for item in drivers
        for line in item.evidence_lines
    ]
    assumptions = [
        MapNode(item.statement, f"Confidence {item.confidence}. Impact if wrong: {item.impact}.")
        for item in drivers
    ]
    constraints = [_constraint_node(case, item, chosen) for item in responsible_constraints(case)]
    expected = case.scenario(chosen.key, "expected")
    headline = expected.headline if expected and expected.headline else "No infrastructure estimate."
    option = MapNode(f"{chosen.key}. {chosen.name}", "The constraints leave this option open.")
    outcome = MapNode(headline, f"Expected outcome of {chosen.name}.")
    decision = MapNode(f"Recommends {chosen.key}. {chosen.name}.", case.decision or "")
    return ReasonMap(
        evidence,
        assumptions,
        constraints,
        option,
        outcome,
        decision,
        _because(case, chosen, expected),
        "",
    )


def render_map(case: DecisionCase) -> str:
    """The reasoning map, in the shape evidence joins assumption, and constraint joins option."""

    diagram = build_map(case)
    if not diagram.ready or diagram.option is None or diagram.outcome is None or diagram.decision is None:
        return diagram.empty if diagram.empty.endswith("\n") else diagram.empty + "\n"
    lines = ["Evidence"]
    for node in diagram.evidence:
        lines.append(node.label)
        if node.detail:
            lines.append(f"  {node.detail}")
    lines.extend(["──────────────┐", "              ↓", "         Assumption"])
    for node in diagram.assumptions:
        lines.append(f"         {node.label}")
        if node.detail:
            lines.append(f"         {node.detail}")
    lines.extend(["              ↓", "Constraint → Option"])
    for node in diagram.constraints:
        lines.append(node.label)
        if node.detail:
            lines.append(f"  {node.detail}")
    lines.append(f"         {diagram.option.label}")
    if diagram.option.detail:
        lines.append(f"         {diagram.option.detail}")
    lines.extend(["              ↓", "          Outcome", f"          {diagram.outcome.label}"])
    if diagram.outcome.detail:
        lines.append(f"          {diagram.outcome.detail}")
    lines.extend(["              ↓", "          Decision", f"          {diagram.decision.label}"])
    if diagram.decision.detail:
        lines.append(f"          {diagram.decision.detail}")
    if diagram.because:
        lines.extend(["", diagram.because])
    return "\n".join(lines) + "\n"


def why(case: DecisionCase | None, asked: str) -> str:
    """Why the recommendation was reached, walked along the stored path."""

    if case is None:
        return "No stored decision is available to trace.\n"
    diagram = build_map(case)
    if not diagram.ready or diagram.option is None:
        return _empty(case)
    lead = f"{diagram.option.label} is the recommendation because this path reaches it."
    lines = [asked, "", case.decision or "Decision", "", lead, "", render_map(case).rstrip()]
    return "\n".join(lines) + "\n"


def _evidence_detail(line: str, item: TrackedAssumption) -> str:
    if line == "No evidence is on record.":
        return item.statement
    return f"Supports {item.statement}"


def _constraint_node(case: DecisionCase, constraint: Constraint, chosen: Option) -> MapNode:
    matched = next((item for item in driving(case) if item.kind == constraint.kind), None)
    label = matched.statement if matched is not None else constraint.statement
    expected = case.scenario(chosen.key, "expected")
    parts: list[str] = []
    if expected is not None and expected.feasible and constraint.kind not in expected.block_codes:
        parts.append(f"Admits {chosen.name}.")
    blocked = _blocked(case, constraint.kind, chosen)
    if blocked:
        parts.append(f"Blocks {_join(blocked)}.")
    return MapNode(label, " ".join(parts))


def _because(case: DecisionCase, chosen: Option, expected: Scenario | None) -> str:
    held = _higher(case, chosen)
    sentences: list[str] = []
    if held:
        verb = "scores" if len(held) == 1 else "score"
        be = "is" if len(held) == 1 else "are"
        kinds = _holding_kinds(case, chosen)
        statements = [_block_phrase(item) for item in responsible_constraints(case) if item.kind in kinds]
        sentences.append(f"{_join(held)} {verb} higher and {be} blocked by {_join(statements)}.")
        sentences.append(f"{chosen.name} is the option those constraints leave open.")
    else:
        sentences.append(f"{chosen.name} is the option the constraints leave open.")
    if expected is not None and expected.headline:
        sentences.append(f"Its expected outcome is {expected.headline}.")
    return " ".join(sentences)


def _holding_kinds(case: DecisionCase, chosen: Option) -> set[str]:
    kinds: set[str] = set()
    expected = case.scenario(chosen.key, "expected")
    if expected is None:
        return kinds
    for option in case.options:
        scenario = case.scenario(option.key, "expected")
        if scenario is None or option.key == chosen.key or scenario.feasible:
            continue
        if scenario.score <= expected.score + 0.01:
            continue
        kinds.update(scenario.block_codes)
    return kinds


def _higher(case: DecisionCase, chosen: Option) -> list[str]:
    expected = case.scenario(chosen.key, "expected")
    if expected is None:
        return []
    names: list[str] = []
    for option in case.options:
        scenario = case.scenario(option.key, "expected")
        if scenario is None or option.key == chosen.key or scenario.feasible:
            continue
        if scenario.score <= expected.score + 0.01:
            continue
        names.append(option.name)
    return names


def _blocked(case: DecisionCase, kind: str, chosen: Option) -> list[str]:
    expected = case.scenario(chosen.key, "expected")
    if expected is None:
        return []
    names: list[str] = []
    for option in case.options:
        scenario = case.scenario(option.key, "expected")
        if scenario is None or option.key == chosen.key or scenario.feasible:
            continue
        if scenario.score <= expected.score + 0.01:
            continue
        if kind in scenario.block_codes:
            names.append(option.name)
    return names


def _chosen(case: DecisionCase) -> Option | None:
    if case.brief is None or not case.brief.recommendation_key:
        return None
    return case.option(case.brief.recommendation_key)


def _empty(case: DecisionCase) -> str:
    if case.brief is not None and case.brief.recommendation_key:
        return "No assumption on record is driving this decision, so the graph has no path to explain.\n"
    return "Nothing is recommended yet, so the graph has no path to explain.\n"


def _block_phrase(constraint: Constraint) -> str:
    if constraint.kind == "timeline":
        return f"the {constraint.statement}"
    return _lower(constraint.statement)


def _lower(text: str) -> str:
    if not text:
        return text
    return text[:1].lower() + text[1:]


def _join(items: list[str]) -> str:
    names = [item for item in items if item]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
