"""Assumptions the recommendation is actually resting on.

Each one names the claim, how much confidence the source supports, what
breaks if the claim is wrong, and the evidence behind it. The link is
assumption, then the option, then the recommendation.
"""

import re

from decision.evidence import reliability
from decision.graph import responsible_constraints
from decision.models import Constraint, DecisionCase, Evidence, Option
from decision.text import plain


class TrackedAssumption:
    def __init__(
        self,
        statement: str,
        confidence: str,
        impact: str,
        impact_detail: str,
        evidence: str,
        option_name: str,
        recommendation: str,
        driving: bool,
        kind: str = "",
        evidence_lines: list[str] | None = None,
    ) -> None:
        self.statement = statement
        self.confidence = confidence
        self.impact = impact
        self.impact_detail = impact_detail
        self.evidence = evidence
        self.evidence_lines = evidence_lines if evidence_lines is not None else [evidence]
        self.option_name = option_name
        self.recommendation = recommendation
        self.driving = driving
        self.kind = kind


def track(case: DecisionCase) -> list[TrackedAssumption]:
    """The assumptions that drive this decision, then any a person recorded."""

    items: list[TrackedAssumption] = []
    chosen = _chosen(case)
    recommendation = _recommendation(case, chosen)
    if chosen is not None:
        duration = _duration(case, chosen, recommendation)
        if duration is not None:
            items.append(duration)
        for constraint in responsible_constraints(case):
            items.append(_constraint(case, constraint, chosen, recommendation))
    seen = {item.statement for item in items}
    for statement in case.assumptions:
        text = statement.strip()
        if not text or text in seen:
            continue
        items.append(
            TrackedAssumption(
                statement=text,
                confidence="Not recorded.",
                impact="Not judged.",
                impact_detail="A person recorded this assumption. Nothing in the estimate scores it.",
                evidence="Recorded on the decision.",
                option_name=chosen.name if chosen else "No option yet.",
                recommendation=recommendation,
                driving=False,
                evidence_lines=["Recorded on the decision."],
            )
        )
    return items


def driving(case: DecisionCase) -> list[TrackedAssumption]:
    return [item for item in track(case) if item.driving]


def render_assumptions(case: DecisionCase) -> str:
    items = track(case)
    if not items:
        if case.brief is None or not case.brief.recommendation_key:
            return "Nothing is recommended yet, so no assumption is driving a choice.\n"
        return "No assumption on record is driving this decision.\n"
    return "\n\n".join(_render(item) for item in items) + "\n"


def answer(case: DecisionCase | None, asked: str) -> str:
    if case is None:
        return "No stored decision is available to trace.\n"
    items = driving(case)
    if not items:
        return "Nothing is recommended yet, so no assumption is driving a choice.\n"
    lines = [asked, "", case.decision or "Decision", ""]
    lines.append(render_assumptions(case).rstrip())
    return "\n".join(lines) + "\n"


def _duration(case: DecisionCase, chosen: Option, recommendation: str) -> TrackedAssumption | None:
    band = _effort(chosen)
    if band is None:
        return None
    _low, mid, high = band
    source = _estimate(case, chosen.key)
    precedent = _precedent(case, chosen)
    limit = _limit(case, "timeline")
    high_impact = limit is not None and high > limit
    detail = f"The expected case is {plain(mid)} weeks."
    if limit is not None and high > limit:
        detail = f"The worst case is {plain(high)} weeks and the limit is {plain(limit)} weeks."
    confidence = "Not recorded."
    lines = ["No estimate is attached to this option."]
    if source is not None:
        confidence = _percent(source.confidence)
        lines = [f"{source.source}, {confidence}."]
    if precedent is not None:
        weeks = _weeks(precedent.statement)
        recorded = f"{precedent.source} recorded a {chosen.name.lower()} in {weeks}" if weeks else precedent.source
        recorded += f", at {_percent(precedent.confidence)} confidence."
        lines.append(recorded)
    return TrackedAssumption(
        statement=f"{chosen.name} is estimated at {plain(mid)} weeks.",
        confidence=confidence,
        impact="High" if high_impact else "Medium",
        impact_detail=detail,
        evidence=" ".join(lines),
        evidence_lines=lines,
        option_name=f"{chosen.key}. {chosen.name}",
        recommendation=recommendation,
        driving=True,
        kind="duration",
    )


def _constraint(
    case: DecisionCase,
    constraint: Constraint,
    chosen: Option,
    recommendation: str,
) -> TrackedAssumption:
    evidence_item = _constraint_evidence(case, constraint)
    confidence = "Assumed"
    evidence = "No evidence is on record."
    if evidence_item is not None:
        confidence = _percent(evidence_item.confidence)
        evidence = evidence_item.source
        if reliability(evidence_item) == "opinion":
            evidence += " (opinion)"
        evidence += f", {confidence}."
    impact, detail = _constraint_impact(case, constraint, chosen)
    return TrackedAssumption(
        statement=_constraint_statement(constraint),
        confidence=confidence,
        impact=impact,
        impact_detail=detail,
        evidence=evidence,
        evidence_lines=[evidence],
        option_name=f"{chosen.key}. {chosen.name}",
        recommendation=recommendation,
        driving=True,
        kind=constraint.kind,
    )


def _constraint_statement(constraint: Constraint) -> str:
    if constraint.kind == "headcount" and constraint.limit is not None:
        noun = "engineer is" if constraint.limit == 1 else "engineers are"
        return f"{plain(constraint.limit)} {noun} available."
    if constraint.kind == "timeline" and constraint.limit is not None:
        unit = "week" if constraint.limit == 1 else "weeks"
        return f"The timeline limit is {plain(constraint.limit)} {unit}."
    if constraint.kind == "downtime" and constraint.limit == 0:
        return "Production downtime is forbidden."
    return constraint.statement


def _constraint_impact(case: DecisionCase, constraint: Constraint, chosen: Option) -> tuple[str, str]:
    blocked = _blocked_names(case, constraint.kind)
    higher = ", ".join(blocked) if blocked else "a higher-scoring option"
    if constraint.kind == "timeline":
        band = _effort(chosen)
        limit = constraint.limit
        if band is not None and limit is not None and band[2] > limit:
            return (
                "High",
                f"The worst case for {chosen.name.lower()} is {plain(band[2])} weeks and the limit is {plain(limit)} weeks.",
            )
    if constraint.kind == "headcount" and constraint.limit is not None and chosen.engineers is not None:
        if chosen.engineers >= constraint.limit:
            needed = _needed(case, "headcount")
            extra = f" {needed} needs more than {plain(constraint.limit)}." if needed else ""
            return (
                "High",
                f"{chosen.name} uses {plain(chosen.engineers)} of the {plain(constraint.limit)} available.{extra}",
            )
    if blocked and _sole_block(case, constraint.kind):
        return ("High", f"{higher} is blocked only by this assumption.")
    if blocked:
        return (
            "Medium",
            f"{higher} is blocked by this assumption, and other blocks remain if it is set aside.",
        )
    return ("Medium", f"{chosen.name} is inside this assumption.")


def _render(item: TrackedAssumption) -> str:
    fields = [
        ("Confidence", item.confidence),
        ("Impact if wrong", f"{item.impact}. {item.impact_detail}"),
        ("Evidence", item.evidence),
    ]
    lines = ["Assumption", item.statement, ""]
    last = len(fields) - 1
    for index, (name, value) in enumerate(fields):
        branch = "└──" if index == last else "├──"
        pad = "    " if index == last else "│   "
        lines.append(f"{branch} {name}")
        lines.append(f"{pad}{value}")
    lines.extend(
        [
            "        ↓",
            "Option",
            item.option_name,
            "        ↓",
            "Recommendation",
            item.recommendation,
        ]
    )
    return "\n".join(lines)


def _chosen(case: DecisionCase) -> Option | None:
    if case.brief is None or not case.brief.recommendation_key:
        return None
    return case.option(case.brief.recommendation_key)


def _recommendation(case: DecisionCase, chosen: Option | None) -> str:
    if chosen is None:
        return "Not recommended yet."
    return f"{chosen.key}. {chosen.name}"


def _estimate(case: DecisionCase, option_key: str) -> Evidence | None:
    linked = [item for item in case.evidence if item.option_key == option_key and item.kind == "estimate"]
    if not linked:
        linked = [item for item in case.evidence if item.option_key == option_key]
    if not linked:
        return None
    return min(linked, key=lambda item: item.confidence)


def _precedent(case: DecisionCase, chosen: Option) -> Evidence | None:
    name = chosen.name.lower()
    for item in case.evidence:
        if item.kind == "precedent" and name in item.statement.lower():
            return item
    return None


def _constraint_evidence(case: DecisionCase, constraint: Constraint) -> Evidence | None:
    for item in case.evidence:
        if item.option_key:
            continue
        text = item.statement.lower()
        if constraint.kind == "headcount" and "engineer" in text:
            return item
        if constraint.kind == "downtime" and "downtime" in text and item.challenges != "downtime":
            return item
        if constraint.kind == "timeline" and item.kind == "constraint" and "week" in text:
            return item
    return None


def _blocked_names(case: DecisionCase, kind: str) -> list[str]:
    chosen = _chosen(case)
    if chosen is None:
        return []
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


def _sole_block(case: DecisionCase, kind: str) -> bool:
    chosen = _chosen(case)
    if chosen is None:
        return False
    expected = case.scenario(chosen.key, "expected")
    if expected is None:
        return False
    for option in case.options:
        scenario = case.scenario(option.key, "expected")
        if scenario is None or option.key == chosen.key or scenario.feasible:
            continue
        if scenario.score <= expected.score + 0.01:
            continue
        if scenario.block_codes == [kind]:
            return True
    return False


def _needed(case: DecisionCase, kind: str) -> str:
    names = _blocked_names(case, kind)
    if len(names) == 1:
        return names[0]
    return ""


def _effort(option: Option) -> tuple[float, float, float] | None:
    for item in option.projections:
        if item.metric_id == "effort":
            return item.p10, item.p50, item.p90
    return None


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _weeks(statement: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s+weeks", statement.lower())
    if match is None:
        return ""
    value = float(match.group(1))
    unit = "week" if value == 1 else "weeks"
    return f"{plain(value)} {unit}"


def _percent(confidence: float) -> str:
    return f"{round(confidence * 100)}%"
