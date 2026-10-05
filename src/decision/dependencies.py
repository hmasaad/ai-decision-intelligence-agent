"""How stored decisions depend on each other.

Edges stay inside one service. A decision can enable, block, depend on,
conflict with, or invalidate another decision. Critical means failure of the
target leaves the source infeasible. A weaker link says the source depends
on the target, and other blocks remain if the target fails.
"""

from decision.evidence import confidence_band
from decision.learn import executed_option
from decision.models import DecisionCase, Evidence, Option


class Dependency:
    def __init__(
        self,
        source: DecisionCase,
        target: DecisionCase,
        relationship: str,
        strength: str,
        confidence: str,
        criticality: str,
        evidence: str,
        note: str,
    ) -> None:
        self.source = source
        self.target = target
        self.relationship = relationship
        self.strength = strength
        self.confidence = confidence
        self.criticality = criticality
        self.evidence = evidence
        self.note = note


def build_dependencies(cases: list[DecisionCase]) -> list[Dependency]:
    edges: list[Dependency] = []
    for source in cases:
        for target in cases:
            if source.id == target.id or not _same_subject(source, target):
                continue
            edges.extend(_pair(source, target))
    return edges


def render_dependencies(cases: list[DecisionCase], focus_id: str = "") -> str:
    focus = _focus(cases, focus_id)
    edges = build_dependencies(cases)
    if focus is not None:
        edges = [item for item in edges if item.source.id == focus.id or item.target.id == focus.id]
        shown = [focus]
    else:
        shown = list(cases)
    if not shown:
        return "No stored decision is available to map.\n"
    blocks: list[str] = []
    for case in shown:
        outgoing = [item for item in edges if item.source.id == case.id]
        blocks.append(_tree(case, outgoing))
    incoming = []
    if focus is not None:
        incoming = [item for item in edges if item.target.id == focus.id and item.source.id != focus.id]
        if incoming:
            grouped: dict[str, list[Dependency]] = {}
            for item in incoming:
                grouped.setdefault(item.source.id, []).append(item)
            blocks.append(
                "From other decisions\n" + "\n\n".join(_tree(group[0].source, group) for group in grouped.values())
            )
    if edges:
        blocks.append(_metadata(edges))
    return "\n\n".join(blocks).rstrip() + "\n"


def page_view(cases: list[DecisionCase], focus_id: str) -> dict[str, object]:
    text = render_dependencies(cases, focus_id)
    edges = [
        item
        for item in build_dependencies(cases)
        if item.source.id == focus_id or item.target.id == focus_id
    ]
    return {
        "text": text,
        "edges": [
            {
                "source": item.source.id,
                "target": item.target.id,
                "relationship": item.relationship,
                "strength": item.strength,
                "confidence": item.confidence,
                "criticality": item.criticality,
                "evidence": item.evidence,
                "note": item.note,
            }
            for item in edges
        ],
    }


def _pair(source: DecisionCase, target: DecisionCase) -> list[Dependency]:
    source_option = executed_option(source)
    target_option = executed_option(target)
    if source_option is None or target_option is None:
        return []
    edges: list[Dependency] = []
    if source_option.key != target_option.key and source.id < target.id:
        edges.append(_conflict(source, target, source_option, target_option))
    target_scene = target.scenario(target_option.key, "expected")
    blocking = _blocking_kinds(source, source_option, target_option)
    if blocking and target_scene is not None and not target_scene.feasible:
        reasons = [reason for reason, code in zip(target_scene.blocked_by, target_scene.block_codes) if code in blocking]
        edges.append(_blocks(source, target, target_option, reasons or target_scene.blocked_by, blocking))
    broken = [kind for kind in _broken_kinds(source_option, target) if kind not in _broken_kinds(target_option, target)]
    if broken:
        edges.append(_invalidates(source, target, source_option, broken))
    lifted, remaining = _lifted(source, target_option, target)
    if lifted:
        edges.append(_enables(source, target, target_option, lifted, remaining))
        if not remaining and target_scene is not None and not target_scene.feasible:
            edges.append(_depends(target, source, target_option, lifted))
    return edges


def _conflict(source: DecisionCase, target: DecisionCase, source_option: Option, target_option: Option) -> Dependency:
    kinds = _shared_constraint_kinds(source, target)
    confidence, evidence = _confidence(source, kinds)
    return Dependency(
        source,
        target,
        "conflicts_with",
        "High",
        confidence,
        "High",
        evidence,
        (
            f"{source_option.key}. {source_option.name} and {target_option.key}. {target_option.name} "
            "cannot both proceed on the same service."
        ),
    )


def _blocks(
    source: DecisionCase,
    target: DecisionCase,
    target_option: Option,
    reasons: list[str],
    codes: list[str],
) -> Dependency:
    confidence, recorded = _confidence(target, codes)
    evidence = " ".join(reasons) if reasons else recorded
    return Dependency(
        source,
        target,
        "blocks",
        "High",
        confidence,
        "High",
        evidence,
        f"{target_option.key}. {target_option.name} stays blocked.",
    )


def _invalidates(source: DecisionCase, target: DecisionCase, source_option: Option, kinds: list[str]) -> Dependency:
    confidence, evidence = _confidence(target, kinds)
    names = _join([_kind_name(target, kind) for kind in kinds])
    return Dependency(
        source,
        target,
        "invalidates",
        "High",
        confidence,
        "Critical",
        evidence,
        (
            f"{source_option.key}. {source_option.name} breaks {names}. "
            f"Failure of {source.id} will invalidate {target.id}."
        ),
    )


def _enables(
    source: DecisionCase,
    target: DecisionCase,
    target_option: Option,
    lifted: list[str],
    remaining: list[str],
) -> Dependency:
    confidence, evidence = _confidence(source, lifted + remaining)
    if remaining:
        strength, criticality = "Medium", "Medium"
        note = (
            f"Admits room for {target_option.key}. {target_option.name} on {_join(lifted)}. "
            f"{_join(remaining)} still blocks it. Failure of {source.id} does not invalidate {target.id}."
        )
    else:
        strength, criticality = "High", "High"
        note = f"Admits {target_option.key}. {target_option.name}."
    return Dependency(source, target, "enables", strength, confidence, criticality, evidence, note)


def _depends(source: DecisionCase, target: DecisionCase, source_option: Option, kinds: list[str]) -> Dependency:
    confidence, evidence = _confidence(target, kinds)
    return Dependency(
        source,
        target,
        "depends_on",
        "High",
        confidence,
        "Critical",
        evidence,
        (
            f"{source.id} critically depends on {target.id}, and failure of {target.id} "
            f"will invalidate {source_option.key}. {source_option.name}."
        ),
    )


def _blocking_kinds(source: DecisionCase, source_option: Option, target_option: Option) -> list[str]:
    kinds: list[str] = []
    headcount = _limit(source, "headcount")
    if (
        headcount is not None
        and source_option.engineers is not None
        and target_option.engineers is not None
        and source_option.engineers >= headcount
        and target_option.engineers > headcount
    ):
        kinds.append("headcount")
    weeks = _limit(source, "timeline")
    if (
        weeks is not None
        and target_option.weeks is not None
        and target_option.weeks > weeks
        and (source_option.weeks is None or source_option.weeks <= weeks)
    ):
        kinds.append("timeline")
    if _limit(source, "downtime") == 0 and not source_option.requires_downtime and target_option.requires_downtime:
        kinds.append("downtime")
    return kinds


def _broken_kinds(option: Option, case: DecisionCase) -> list[str]:
    kinds: list[str] = []
    for constraint in case.constraints:
        if constraint.kind == "headcount" and option.engineers is not None and constraint.limit is not None:
            if option.engineers > constraint.limit:
                kinds.append("headcount")
        elif constraint.kind == "timeline" and option.weeks is not None and constraint.limit is not None:
            if option.weeks > constraint.limit:
                kinds.append("timeline")
        elif constraint.kind == "downtime" and constraint.limit == 0 and option.requires_downtime:
            kinds.append("downtime")
    return kinds


def _lifted(source: DecisionCase, option: Option, target: DecisionCase) -> tuple[list[str], list[str]]:
    """Blocks on the target option that the source constraints would lift, and those that remain."""

    scene = target.scenario(option.key, "expected")
    if scene is None or scene.feasible or not scene.block_codes:
        return [], []
    lifted: list[str] = []
    remaining: list[str] = []
    for kind in scene.block_codes:
        if _source_admits(source, option, kind):
            lifted.append(kind)
        else:
            remaining.append(kind)
    return lifted, remaining


def _source_admits(source: DecisionCase, option: Option, kind: str) -> bool:
    limit = _limit(source, kind)
    if kind == "headcount":
        return limit is not None and option.engineers is not None and option.engineers <= limit
    if kind == "timeline":
        return limit is not None and option.weeks is not None and option.weeks <= limit
    if kind == "downtime":
        return limit != 0
    return False


def _confidence(case: DecisionCase, kinds: list[str]) -> tuple[str, str]:
    lines: list[str] = []
    weakest = "High"
    order = {"Low": 1, "Medium": 2, "High": 3}
    for kind in dict.fromkeys(kinds):
        found = _constraint_evidence(case, kind)
        if not found:
            lines.append(f"No evidence is on record for {_kind_name(case, kind)}.")
            weakest = "Low"
            continue
        item = min(found, key=lambda claim: claim.confidence)
        band = _band(item.confidence)
        if order[band] < order[weakest]:
            weakest = band
        opinion = " (opinion)" if item.kind in {"opinion", "stakeholder"} or item.channel == "customer_feedback" else ""
        lines.append(f"{item.source}{opinion}, {round(item.confidence * 100)}%.")
    if not lines:
        return "Low", "No evidence is on record."
    return weakest, " ".join(lines)


def _constraint_evidence(case: DecisionCase, kind: str) -> list[Evidence]:
    found: list[Evidence] = []
    for item in case.evidence:
        if item.option_key:
            continue
        text = item.statement.lower()
        if kind == "headcount" and "engineer" in text:
            found.append(item)
        elif kind == "downtime" and "downtime" in text:
            found.append(item)
        elif kind == "timeline" and item.kind == "constraint" and "week" in text:
            found.append(item)
    return found


def _tree(case: DecisionCase, edges: list[Dependency]) -> str:
    lines = [case.id, case.decision or "Not stated."]
    if not edges:
        lines.append("No other stored decision is linked.")
        return "\n".join(lines)
    lines.append("│")
    for index, edge in enumerate(edges):
        last = index == len(edges) - 1
        joint = "└── " if last else "├── "
        lines.append(f"{joint}{edge.relationship} → {edge.target.id}")
        nest = "    " if last else "│   "
        lines.append(f"{nest}{edge.note}")
    return "\n".join(lines)


def _metadata(edges: list[Dependency]) -> str:
    blocks: list[str] = []
    for edge in edges:
        blocks.append(
            "\n".join(
                [
                    "Dependency",
                    f"Source             {edge.source.id}",
                    f"Target             {edge.target.id}",
                    f"Relationship type  {edge.relationship}",
                    f"Strength           {edge.strength}",
                    f"Confidence         {edge.confidence}",
                    f"Criticality        {edge.criticality}",
                    f"Evidence           {edge.evidence}",
                    edge.note,
                ]
            )
        )
    return "\n\n".join(blocks)


def _shared_constraint_kinds(left: DecisionCase, right: DecisionCase) -> list[str]:
    right_kinds = {item.kind for item in right.constraints}
    return [item.kind for item in left.constraints if item.kind in right_kinds]


def _kind_name(case: DecisionCase, kind: str) -> str:
    for item in case.constraints:
        if item.kind == kind:
            if kind == "downtime":
                return "the downtime ban"
            if kind == "timeline":
                return f"the {item.statement}"
            return item.statement
    return kind


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
    return cases[0] if cases else None


def _band(value: float) -> str:
    return confidence_band(value).capitalize()


def _join(items: list[str]) -> str:
    names = [item for item in items if item]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
