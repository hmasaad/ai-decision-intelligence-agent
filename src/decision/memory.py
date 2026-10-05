"""Reconstruct a decision from the record, including months later.

The case is the memory. This module only reads it: why the call was made,
which evidence and assumptions it used, what was rejected, who approved it,
what happened, and what was learned.
"""

from decision.models import DecisionCase
from decision.text import format_amount
from decision.uncertainty import judgments


class Memory:
    def __init__(
        self,
        decision: str,
        why: str,
        evidence: list[str],
        assumptions: list[str],
        rejected: list[str],
        approved: str,
        afterward: list[str],
        learned: str,
    ) -> None:
        self.decision = decision
        self.why = why
        self.evidence = evidence
        self.assumptions = assumptions
        self.rejected = rejected
        self.approved = approved
        self.afterward = afterward
        self.learned = learned


def remember(case: DecisionCase) -> Memory:
    return Memory(
        decision=case.decision or "Not stated.",
        why=_why(case),
        evidence=_evidence(case),
        assumptions=_assumptions(case),
        rejected=_rejected(case),
        approved=_approved(case),
        afterward=_afterward(case),
        learned=_learned(case),
    )


def recall(cases: list[DecisionCase], question: str) -> str:
    """Answer a why-did-we-choose question from stored decisions."""

    asked = " ".join(question.split())
    if not asked:
        return "Ask which choice you want reconstructed.\n"
    match = _match(cases, asked)
    if match is None:
        return (
            "No stored decision chose those options. "
            "Memory only answers from decisions recorded in this workspace.\n"
        )
    item = remember(match)
    return f"{asked}\n\n{render_memory(item)}"


def render_memory(item: Memory) -> str:
    return (
        "DECISION\n"
        f"{item.decision}\n\n"
        "WHY IT WAS MADE\n"
        f"{item.why}\n\n"
        "EVIDENCE\n"
        f"{_lines(item.evidence)}\n\n"
        "ASSUMPTIONS\n"
        f"{_lines(item.assumptions)}\n\n"
        "REJECTED\n"
        f"{_lines(item.rejected)}\n\n"
        "APPROVED BY\n"
        f"{item.approved}\n\n"
        "AFTERWARD\n"
        f"{_lines(item.afterward)}\n\n"
        "LEARNED\n"
        f"{item.learned}\n"
    )


def _why(case: DecisionCase) -> str:
    objective = case.objective.strip() or "The objective was not stated."
    if case.brief is None or not case.brief.rationale:
        return objective
    return f"{objective} {case.brief.rationale[0]}"


def _evidence(case: DecisionCase) -> list[str]:
    ranked = [
        item
        for item in case.evidence
        if item.value is not None and item.option_key is None and item.confidence >= 0.75
    ]
    order = {"infra_cost": 0, "deploy_time": 1, "incident_rate": 2}
    ranked.sort(key=lambda item: (order.get(item.metric_id or "", 9), -item.confidence))
    lines = [item.statement for item in ranked[:3]]
    return lines or ["No measured evidence is on record."]


def _assumptions(case: DecisionCase) -> list[str]:
    lines = [
        f"{item.label}: {item.display}. {item.basis}"
        for item in judgments(case)
        if item.stance in {"assumed", "unknown"}
    ]
    return lines or ["No assumption is marked on this decision."]


def _rejected(case: DecisionCase) -> list[str]:
    chosen = case.brief.recommendation_key if case.brief else None
    lines: list[str] = []
    for option in case.options:
        if option.key == chosen:
            continue
        expected = case.scenario(option.key, "expected")
        if expected is None:
            lines.append(f"{option.key}. {option.name} — not scored.")
        elif expected.blocked_by:
            lines.append(f"{option.key}. {option.name} — {' '.join(expected.blocked_by)}")
        else:
            lines.append(f"{option.key}. {option.name} — fits the constraints and scores lower.")
    return lines or ["No alternative is on record."]


def _approved(case: DecisionCase) -> str:
    if case.review_action not in {"approved", "modified"}:
        return "Not approved yet. The brief is waiting for a person."
    when = case.reviewed_at[:10] if case.reviewed_at else "an unrecorded date"
    who = case.approved_by or "a person whose name was not recorded"
    if case.review_action == "modified":
        picked = case.option(case.human_choice) if case.human_choice else None
        choice = f"{picked.key}. {picked.name}" if picked is not None else "another option"
        recommended = ""
        if case.brief is not None and case.brief.recommendation_key:
            option = case.option(case.brief.recommendation_key)
            if option is not None:
                recommended = f" The agent recommended {option.key}. {option.name}."
        line = f"Modified by {who} on {when}.{recommended} The person chose {choice}."
    else:
        line = f"Approved by {who} on {when}."
    if case.review_note:
        line += f" Note: {case.review_note}."
    if case.asked_by:
        line += f" Asked by {case.asked_by}."
    return line


def _afterward(case: DecisionCase) -> list[str]:
    if not case.outcomes:
        return ["Nothing has been recorded yet."]
    lines: list[str] = []
    for outcome in case.outcomes:
        metric = case.metric(outcome.metric_id)
        if metric is None:
            continue
        lines.append(
            f"{metric.name}: predicted {format_amount(metric, outcome.predicted)}, "
            f"actual {format_amount(metric, outcome.actual)}, variance {outcome.variance}."
        )
    return lines


def _learned(case: DecisionCase) -> str:
    if case.lesson is None:
        return "The lesson has not been written."
    return case.lesson.reason


def _match(cases: list[DecisionCase], question: str) -> DecisionCase | None:
    text = question.lower()
    left, right = _split(text)
    best: tuple[int, DecisionCase] | None = None
    for case in cases:
        score = _score(case, text, left, right)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, case)
    return None if best is None else best[1]


def _split(text: str) -> tuple[str, str]:
    for marker in ("instead of", "rather than", " versus ", " vs "):
        if marker in text:
            left, right = text.split(marker, 1)
            return left, right
    return text, ""


def _score(case: DecisionCase, text: str, left: str, right: str) -> int:
    chosen = ""
    if case.brief and case.brief.recommendation_key:
        option = case.option(case.brief.recommendation_key)
        chosen = option.name.lower() if option else ""
    names = [option.name.lower() for option in case.options]
    score = 0
    if chosen and chosen in left:
        score += 3
    elif chosen and chosen in text:
        score += 1
    if right:
        if any(name != chosen and name in right for name in names):
            score += 3
        else:
            return 0
    subject = case.subject.lower()
    if subject and subject in text:
        score += 1
    return score


def _lines(items: list[str]) -> str:
    return "\n".join(f"• {line}" for line in items)
