"""The recommendation, the confidence behind it, and what would move that confidence.

The percent is the weaker source on the expected return. A word such as
medium does not replace it. Risks are the ones already on the decision.
"""

from decision.models import DecisionCase, Option
from decision.text import plain
from decision.uncertainty import judgments, return_confidence
from decision.whatif import answer

FLOOR = 0.60


class ConfidenceReport:
    def __init__(
        self,
        recommendation: str,
        percent: str,
        word: str,
        basis: str,
        risks: list[tuple[str, str]],
        below: str,
        conditions: list[str],
    ) -> None:
        self.recommendation = recommendation
        self.percent = percent
        self.word = word
        self.basis = basis
        self.risks = risks
        self.below = below
        self.conditions = conditions


def build_confidence(case: DecisionCase) -> ConfidenceReport:
    """Recommendation, percent, main risks, and the moves that lower confidence."""

    chosen = _chosen(case)
    if chosen is None:
        return ConfidenceReport(
            recommendation="Not recommended yet.",
            percent="Not scored yet.",
            word="",
            basis="",
            risks=[],
            below="Nothing is scored yet, so there is no confidence to move.",
            conditions=[],
        )
    value = return_confidence(case, chosen.key)
    percent = _percent(value)
    word = case.brief.confidence if case.brief else ""
    basis = _basis(case, chosen)
    risks = [(risk.title, risk.detail) for risk in case.risks]
    below, conditions = _conditions(case, value)
    return ConfidenceReport(
        recommendation=f"{chosen.key}. {chosen.name}",
        percent=percent,
        word=word,
        basis=basis,
        risks=risks,
        below=below,
        conditions=conditions,
    )


def confidence_label(case: DecisionCase) -> str:
    """Short label for a decision list: the percent, then the brief's word."""

    chosen = _chosen(case)
    if chosen is None:
        if case.brief is None:
            return "Not briefed"
        return case.brief.confidence or "Not briefed"
    word = case.brief.confidence if case.brief else ""
    percent = _percent(return_confidence(case, chosen.key))
    if word:
        return f"{percent} · {word}"
    return percent


def render_confidence(case: DecisionCase) -> str:
    report = build_confidence(case)
    lines = [
        "Recommendation",
        report.recommendation,
        "",
        "Confidence",
        report.percent,
    ]
    detail = " ".join(part for part in (report.word.capitalize() + "." if report.word else "", report.basis) if part)
    if detail:
        lines.append(detail)
    lines.extend(["", "Main risks"])
    if not report.risks:
        lines.append("None recorded.")
    for index, (title, detail) in enumerate(report.risks, start=1):
        lines.append(f"{index}. {title}")
        if detail:
            lines.append(f"   {detail}")
    lines.extend(["", report.below])
    for item in report.conditions:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _conditions(case: DecisionCase, current: float | None) -> tuple[str, list[str]]:
    if current is None:
        return "Confidence is not on record.", []
    percent = _percent(current)
    if current < FLOOR:
        lead = f"Confidence is {percent}, below 60%."
        hinge = "It falls further if:"
    else:
        lead = "Confidence would fall below 60% if:"
        hinge = ""
    engineers = _limit(case, "headcount")
    weeks = _limit(case, "timeline")
    found: list[str] = []
    if weeks is not None and engineers is not None:
        stretched = answer(
            case,
            engineers=engineers,
            from_engineers=engineers,
            weeks=weeks + 1,
            from_weeks=weeks,
        )
        line = _timeline_line(weeks, stretched)
        if line:
            found.append(line)
        if engineers > 1:
            shorter = answer(case, engineers=engineers - 1, from_engineers=engineers, from_weeks=weeks)
            line = _capacity_line(engineers, shorter)
            if line:
                found.append(line)
    if not found:
        return lead, []
    if hinge:
        return f"{lead} {hinge}", found
    return lead, found


def _timeline_line(weeks: float, item) -> str:
    if item is None:
        return ""
    after = _after_confidence(item)
    if not after:
        return ""
    unit = "week" if weeks + 1 == 1 else "weeks"
    recorded = "week" if weeks == 1 else "weeks"
    return (
        f"The timeline moves off the recorded {plain(weeks)} {recorded}. "
        f"At {plain(weeks + 1)} {unit}, confidence is {after}."
    )


def _capacity_line(engineers: float, item) -> str:
    if item is None:
        return ""
    after = _after_confidence(item)
    timeline = _step_after(item, "Timeline")
    if not after or not timeline:
        return ""
    noun = "engineer" if engineers - 1 == 1 else "engineers"
    recorded = "engineer" if engineers == 1 else "engineers"
    moved = ""
    if item.changed:
        moved = f" The recommendation moves to {item.recommendation_after}."
    return (
        f"Engineering capacity drops below {plain(engineers)} {recorded}. "
        f"At {plain(engineers - 1)} {noun}, the timeline derives to {timeline}, and confidence is {after}.{moved}"
    )


def _after_confidence(item) -> str:
    step = _step(item, "Decision confidence")
    if step is None:
        return ""
    return step.after


def _step_after(item, label: str) -> str:
    step = _step(item, label)
    if step is None:
        return ""
    return step.after


def _step(item, label: str):
    for step in item.steps:
        if step.label == label:
            return step
    return None


def _basis(case: DecisionCase, chosen: Option) -> str:
    for item in judgments(case, chosen.key):
        if item.id == "return":
            return item.basis
    return ""


def _chosen(case: DecisionCase) -> Option | None:
    if case.brief is None or not case.brief.recommendation_key:
        return None
    return case.option(case.brief.recommendation_key)


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _percent(value: float | None) -> str:
    if value is None:
        return "Not scored yet."
    return f"{round(value * 100)}%"
