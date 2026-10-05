"""The stop between a recommendation and execution.

The agent analyzes and recommends. A person approves, rejects, or modifies
that recommendation, and their reasoning is stored with the decision.
Execution starts from the option the person accepted.
"""

from decision.models import DecisionCase, Option
from decision.uncertainty import return_confidence


class GateStep:
    def __init__(self, label: str, detail: str, note: str = "") -> None:
        self.label = label
        self.detail = detail
        self.note = note


def build_gate(case: DecisionCase) -> list[GateStep]:
    """The five steps from analysis to execution, filled from the record."""

    return [
        GateStep("Agent analyzes", _analyzed(case)),
        GateStep("Agent recommends", *_recommended(case)),
        GateStep("Human reviews", _reviewer(case)),
        GateStep("Approve / Reject / Modify", *_decision(case)),
        GateStep("Execution", _execution(case)),
    ]


def render_gate(case: DecisionCase) -> str:
    lines: list[str] = []
    steps = build_gate(case)
    for index, step in enumerate(steps):
        lines.append(step.label)
        lines.append(step.detail)
        if step.note:
            lines.append(step.note)
        if index < len(steps) - 1:
            lines.append("↓")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _analyzed(case: DecisionCase) -> str:
    if case.brief is not None:
        return "The brief is written."
    if case.scenarios:
        return "The options are scored. The brief is not written."
    return "Analysis has not been written."


def _recommended(case: DecisionCase) -> tuple[str, str]:
    if case.brief is None or not case.brief.recommendation_key:
        return "Not recommended yet.", ""
    option = case.option(case.brief.recommendation_key)
    if option is None:
        return "Not recommended yet.", ""
    value = return_confidence(case, option.key)
    note = f"Confidence {round(value * 100)}%." if value is not None else ""
    return f"{option.key}. {option.name}.", note


def _reviewer(case: DecisionCase) -> str:
    if not case.review_action:
        return "Waiting for a person."
    who = case.approved_by.strip() or "A person whose name was not recorded"
    when = case.reviewed_at[:10] if case.reviewed_at else ""
    if when:
        return f"{who} on {when}."
    return f"{who}."


def _decision(case: DecisionCase) -> tuple[str, str]:
    if not case.review_action:
        return "No decision recorded.", ""
    chosen = _choice(case)
    name = f"{chosen.key}. {chosen.name}." if chosen is not None else ""
    labels = {
        "approved": "Approved.",
        "rejected": "Rejected.",
        "deferred": "Deferred.",
        "modified": "Modified.",
    }
    detail = labels.get(case.review_action, case.review_action)
    if name and case.review_action in {"approved", "modified"}:
        detail = f"{detail} {name}"
    notes: list[str] = []
    if case.review_action == "modified":
        recommended = _recommended_name(case)
        if recommended:
            notes.append(f"The agent recommended {recommended}.")
    if case.review_note.strip():
        reasoning = case.review_note.strip()
        if reasoning[-1] not in ".!?":
            reasoning += "."
        notes.append(f"Reasoning: {reasoning}")
    else:
        notes.append("Reasoning was not recorded.")
    if case.review_action == "modified" and chosen is not None:
        scene = case.scenario(chosen.key, "expected")
        if scene is not None and not scene.feasible and scene.blocked_by:
            notes.append(" ".join(scene.blocked_by))
    return detail, " ".join(notes)


def _execution(case: DecisionCase) -> str:
    if case.execution:
        if case.review_action == "modified":
            return "The plan follows the option the person chose."
        return "The plan follows the recommendation."
    if case.review_action in {"rejected", "deferred"}:
        return "Execution does not start."
    return "Execution waits for a person."


def _choice(case: DecisionCase) -> Option | None:
    key = case.human_choice or ""
    if not key and case.review_action == "approved" and case.brief is not None:
        key = case.brief.recommendation_key
    if not key:
        return None
    return case.option(key)


def _recommended_name(case: DecisionCase) -> str:
    if case.brief is None or not case.brief.recommendation_key:
        return ""
    option = case.option(case.brief.recommendation_key)
    if option is None:
        return ""
    return f"{option.key}. {option.name}"
