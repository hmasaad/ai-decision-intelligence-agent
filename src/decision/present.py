"""View models for the command line and the decision board."""

from decision.evidence import balance_lines, confidence_band, coverage, freshness, reliability, stance_text
from decision.loop import HUMAN, gaps
from decision.models import CHANNELS, DecisionCase, Stage
from decision.text import format_amount, format_span, plain, render_frame
from decision.alternatives import compare
from decision.assumptions import track
from decision.confidence import build_confidence
from decision.scenarios import build_engine
from decision.graph import build_graph
from decision.reason import build_map
from decision.memory import remember
from decision.uncertainty import judgments
from decision.whatif import opening, posed

ROLE_LABELS = {
    "status_quo": "Status quo",
    "hybrid": "Hybrid",
    "replacement": "Replacement",
    "alternative": "Alternative",
}

LOOP = (
    ("request", "Decision request"),
    ("evidence", "Context & evidence"),
    ("frame", "Decision framing"),
    ("model", "Alternatives & constraints"),
    ("simulate", "Scenario simulation"),
    ("risk", "Risk & confidence"),
    ("brief", "Decision brief"),
    ("human", "Human decision"),
    ("execute", "Execute decision"),
    ("outcome", "Outcome tracking"),
    ("learn", "Learn & re-evaluate"),
)

LATER = {"execute", "outcome", "learn"}
STOPPED = {Stage.rejected, Stage.deferred}


def progress(case: DecisionCase) -> list[dict[str, str]]:
    flags = _flags(case)
    items: list[dict[str, str]] = []
    for key, label in LOOP:
        if case.status in STOPPED and key in LATER:
            state = "skipped"
        elif flags[key]:
            state = "done"
        else:
            state = "todo"
        items.append({"id": key, "label": label, "state": state})
    for item in items:
        if item["state"] == "todo":
            item["state"] = "current"
            break
    return items


def option_columns(case: DecisionCase) -> list[dict[str, object]]:
    columns: list[dict[str, object]] = []
    for option in case.options:
        expected = case.scenario(option.key, "expected")
        downside = case.scenario(option.key, "pessimistic")
        columns.append(
            {
                "key": option.key,
                "name": option.name,
                "summary": option.summary,
                "feasible": bool(expected and expected.feasible),
                "blocked": list(expected.blocked_by) if expected else [],
                "downside": list(downside.blocked_by) if downside and not downside.feasible else [],
                "score": f"{expected.score:.2f}" if expected else "—",
                "engineers": plain(option.engineers) if option.engineers is not None else "Not set",
                "weeks": plain(option.weeks) if option.weeks is not None else "Not set",
                "downtime": _downtime(option.requires_downtime),
                "role": ROLE_LABELS.get(option.role, ""),
                "recommended": bool(case.brief and case.brief.recommendation_key == option.key),
            }
        )
    return columns


def metric_rows(case: DecisionCase) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric in case.metrics:
        cells: list[str] = []
        for option in case.options:
            band = next(
                (item for item in case.bands if item.option_key == option.key and item.metric_id == metric.id),
                None,
            )
            if band is None:
                cells.append("No estimate")
            else:
                cells.append(
                    f"{format_amount(metric, band.mid)} ({format_span(metric, band.low, band.high)})"
                )
        rows.append({"name": metric.name, "weight": metric.weight, "cells": cells})
    return rows


def dossier(case: DecisionCase) -> dict[str, object]:
    return {
        "frame_text": render_frame(case),
        "gaps": gaps(case),
        "progress": progress(case),
        "columns": option_columns(case),
        "rows": metric_rows(case),
        "ready": case.brief is not None,
        "steps_done": bool(case.execution) and all(step.status == "done" for step in case.execution),
        "outcomes": outcome_lines(case),
        "claims": claim_views(case),
        "balance": balance_lines(case),
        "sources": coverage(case.evidence),
        "trees": scenario_trees(case),
        "judgments": judgment_views(case),
        "whatif": whatif_view(posed(case)),
        "opening": opening(case),
        "memory": memory_view(case),
        "graph": build_graph(case).layers(),
        "reason": _reason_view(case),
        "assumptions": _assumption_views(track(case)),
        "comparison": _comparison_view(case),
        "engine": _engine_view(case),
        "confidence": _confidence_view(case),
    }


def _reason_view(case: DecisionCase) -> dict[str, object]:
    diagram = build_map(case)
    if not diagram.ready or diagram.option is None or diagram.outcome is None or diagram.decision is None:
        return {"ready": False, "empty": diagram.empty.strip()}
    return {
        "ready": True,
        "evidence": [{"label": node.label, "detail": node.detail} for node in diagram.evidence],
        "assumptions": [{"label": node.label, "detail": node.detail} for node in diagram.assumptions],
        "constraints": [{"label": node.label, "detail": node.detail} for node in diagram.constraints],
        "option": {"label": diagram.option.label, "detail": diagram.option.detail},
        "outcome": {"label": diagram.outcome.label, "detail": diagram.outcome.detail},
        "decision": {"label": diagram.decision.label, "detail": diagram.decision.detail},
        "because": diagram.because,
    }


def _comparison_view(case: DecisionCase) -> dict[str, object]:
    found = compare(case)
    return {
        "slots": [{"label": label, "value": value} for label, value in found.slots],
        "also": found.also,
        "basis": found.basis,
        "reading": found.reading,
        "rows": [
            {
                "label": row.label,
                "role": row.role,
                "cost": row.cost,
                "time": row.time,
                "risk": row.risk,
                "value": row.value,
                "note": row.note,
                "recommended": row.recommended,
            }
            for row in found.rows
        ],
    }


def _confidence_view(case: DecisionCase) -> dict[str, object]:
    report = build_confidence(case)
    return {
        "recommendation": report.recommendation,
        "percent": report.percent,
        "word": report.word,
        "basis": report.basis,
        "risks": [{"title": title, "detail": detail} for title, detail in report.risks],
        "below": report.below,
        "conditions": report.conditions,
    }


def _engine_view(case: DecisionCase) -> dict[str, object]:
    engine = build_engine(case)
    return {
        "option": engine.option,
        "ready": engine.ready,
        "reading": engine.reading,
        "cases": [{"name": item.name, "headline": item.headline, "note": item.note} for item in engine.cases],
        "variables": [{"name": item.name, "detail": item.detail} for item in engine.variables],
        "chain": [{"label": step.label, "change": step.change, "note": step.note} for step in engine.chain],
    }


def _assumption_views(items: list) -> list[dict[str, str]]:
    return [
        {
            "statement": item.statement,
            "confidence": item.confidence,
            "impact": item.impact,
            "impact_detail": item.impact_detail,
            "evidence": item.evidence,
            "option_name": item.option_name,
            "recommendation": item.recommendation,
            "driving": "yes" if item.driving else "",
        }
        for item in items
    ]


def memory_view(case: DecisionCase) -> dict[str, object]:
    item = remember(case)
    return {
        "decision": item.decision,
        "why": item.why,
        "evidence": item.evidence,
        "assumptions": item.assumptions,
        "rejected": item.rejected,
        "approved": item.approved,
        "afterward": item.afterward,
        "learned": item.learned,
    }


def judgment_views(case: DecisionCase) -> list[dict[str, str]]:
    views: list[dict[str, str]] = []
    for item in judgments(case):
        views.append(
            {
                "label": item.label,
                "display": item.display,
                "stance": item.stance.capitalize(),
                "stance_key": item.stance,
                "confidence": item.percent,
                "basis": item.basis,
            }
        )
    return views


def whatif_view(item: object) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "question": item.question,
        "steps": [
            {"label": step.label, "before": step.before, "after": step.after, "note": step.note}
            for step in item.steps
        ],
        "recommendation_before": item.recommendation_before,
        "recommendation_after": item.recommendation_after,
        "changed": item.changed,
        "from_engineers": _field(item.from_engineers),
        "engineers": _field(item.engineers),
        "from_weeks": _field(item.from_weeks),
        "weeks": _field(item.weeks),
        "downtime": item.downtime,
    }


def _field(value: float | None) -> str:
    if value is None:
        return ""
    return plain(value)


def scenario_trees(case: DecisionCase) -> list[dict[str, object]]:
    from decision.simulate import BASE_CASES, STRESS_CASES

    trees: list[dict[str, object]] = []
    for option in case.options:
        cases = [_case_view(case, option.key, name) for name in BASE_CASES]
        stresses = [_case_view(case, option.key, name) for name in STRESS_CASES]
        if any(item is not None for item in cases):
            trees.append(
                {
                    "key": option.key,
                    "name": option.name,
                    "cases": [item for item in cases if item is not None],
                    "stresses": [item for item in stresses if item is not None],
                }
            )
    return trees


def _case_view(case: DecisionCase, key: str, name: str) -> dict[str, object] | None:
    scenario = case.scenario(key, name)
    if scenario is None:
        return None
    return {
        "label": scenario.label,
        "headline": scenario.headline,
        "detail": scenario.detail,
        "feasible": scenario.feasible,
        "kind": "loss" if scenario.headline.endswith("loss") else "benefit" if scenario.headline.endswith("benefit") else "unchanged",
    }


def claim_views(case: DecisionCase, as_of=None) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for item in case.evidence:
        band = confidence_band(item.confidence)
        grade = reliability(item)
        claims.append(
            {
                "claim": item.statement,
                "source": f"{CHANNELS.get(item.channel, item.channel)} · {item.source}",
                "timestamp": item.observed_at.isoformat(),
                "reliability": grade.capitalize(),
                "reliability_key": grade,
                "confidence": f"{band.capitalize()} · {item.confidence:.2f}",
                "freshness": freshness(item.observed_at, as_of).capitalize(),
                "stance": stance_text(case, item),
            }
        )
    return claims


def outcome_lines(case: DecisionCase) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for outcome in case.outcomes:
        metric = case.metric(outcome.metric_id)
        if metric is None:
            continue
        lines.append(
            {
                "name": metric.name,
                "actual": format_amount(metric, outcome.actual),
                "predicted": format_amount(metric, outcome.predicted),
                "variance": outcome.variance,
                "cause": outcome.cause,
                "learning": outcome.learning,
            }
        )
    return lines


def _flags(case: DecisionCase) -> dict[str, bool]:
    steps_done = bool(case.execution) and all(step.status == "done" for step in case.execution)
    return {
        "request": bool(case.request),
        "evidence": bool(case.evidence),
        "frame": bool(case.decision),
        "model": bool(case.options) and bool(case.constraints),
        "simulate": bool(case.scenarios),
        "risk": case.brief is not None,
        "brief": case.brief is not None,
        "human": case.status in HUMAN,
        "execute": steps_done or case.status in {Stage.tracking, Stage.learned},
        "outcome": bool(case.outcomes),
        "learn": case.lesson is not None,
    }


def _downtime(value: bool | None) -> str:
    if value is None:
        return "Not set"
    return "Required" if value else "Not required"
