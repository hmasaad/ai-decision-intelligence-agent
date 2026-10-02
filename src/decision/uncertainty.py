"""How sure each number is, and what kind of number it is.

A range is not a confidence. The range is how wide the estimate is. The
confidence is how much the source behind it can be trusted. A figure with
neither is unknown, and it stays blank.
"""

from decision.models import DecisionCase, Evidence, Option
from decision.text import format_span, plain

STANCES = ("known", "estimated", "inferred", "assumed", "unknown")


class Judgment:
    """One figure on the decision, with its stance and confidence."""

    def __init__(
        self,
        id: str,
        label: str,
        stance: str,
        display: str,
        basis: str,
        confidence: float | None = None,
    ) -> None:
        if stance not in STANCES:
            raise ValueError(f"Unknown stance {stance}")
        self.id = id
        self.label = label
        self.stance = stance
        self.display = display
        self.basis = basis
        self.confidence = confidence

    @property
    def percent(self) -> str:
        if self.confidence is None:
            return "—"
        return f"{round(self.confidence * 100)}%"


def judgments(case: DecisionCase, key: str | None = None) -> list[Judgment]:
    """Classify the figures the recommendation actually rests on."""

    if key is None and case.brief is not None:
        key = case.brief.recommendation_key
    chosen = case.option(key) if key else None
    items: list[Judgment] = []
    items.append(_return_judgment(case, chosen))
    if chosen is not None:
        items.append(_duration(case, chosen))
        items.append(_future_cost(case, chosen))
    current = _measured(case, "infra_cost")
    if current is not None:
        items.append(current)
    engineers = _engineers(case)
    if engineers is not None:
        items.append(engineers)
    timeline = _timeline(case)
    if timeline is not None:
        items.append(timeline)
    items.append(_labor())
    return items


def return_confidence(case: DecisionCase, key: str | None) -> float | None:
    for item in judgments(case, key):
        if item.id == "return":
            return item.confidence
    return None


def _return_judgment(case: DecisionCase, chosen: Option | None) -> Judgment:
    benefit = _annual_benefit(case, chosen)
    if benefit is None or chosen is None:
        return Judgment(
            "return",
            "Expected return",
            "unknown",
            "Unknown",
            "The return needs a recommended option and an infrastructure estimate.",
        )
    kind = "benefit" if benefit > 0 else "loss" if benefit < 0 else "change"
    amount = "No change" if abs(benefit) < 1 else f"${abs(benefit):,.0f} {kind} a year"
    measured = _evidence_metric(case, "infra_cost")
    estimated = _estimate_confidence(case, chosen.key)
    inputs = [item for item in (measured, estimated) if item is not None]
    confidence = min(item.confidence for item in inputs) if inputs else None
    if measured is None or estimated is None:
        basis = "One side of this difference has no source, so the return stays unmarked."
        stance = "unknown" if confidence is None else "inferred"
    else:
        stance = "inferred"
        basis = (
            f"Inferred from today's infrastructure cost ({measured.percent} {measured.stance}) "
            f"and the estimated cost of {chosen.name} ({estimated.percent} {estimated.stance}). "
            "The return takes the lower of the two."
        )
    return Judgment("return", "Expected return", stance, amount, basis, confidence)


def _duration(case: DecisionCase, chosen: Option) -> Judgment:
    metric = case.metric("effort")
    band = _band(chosen, "effort")
    source = _estimate_confidence(case, chosen.key)
    if metric is None or band is None:
        return Judgment(
            "duration",
            "Migration duration",
            "unknown",
            "Unknown",
            f"{chosen.name} has no effort estimate.",
        )
    low, _mid, high = band
    display = format_span(metric, low, high) if low != high else f"{plain(low)} weeks"
    if source is None:
        return Judgment(
            "duration",
            "Migration duration",
            "unknown",
            display,
            "The range is on the option, and no source is attached to it.",
        )
    return Judgment(
        "duration",
        "Migration duration",
        "estimated",
        display,
        f"{source.basis} The range is the estimate. The percent is how much that source is trusted.",
        source.confidence,
    )


def _future_cost(case: DecisionCase, chosen: Option) -> Judgment:
    metric = case.metric("infra_cost")
    band = _band(chosen, "infra_cost")
    source = _estimate_confidence(case, chosen.key)
    if metric is None or band is None:
        return Judgment(
            "cost",
            "Infrastructure cost",
            "unknown",
            "Unknown",
            f"{chosen.name} has no cost estimate.",
        )
    low, mid, high = band
    display = format_span(metric, low, high) if low != high else f"${mid:,.0f} per month"
    if source is None:
        return Judgment(
            "cost",
            "Infrastructure cost",
            "unknown",
            display,
            "The range is on the option, and no source is attached to it.",
        )
    return Judgment(
        "cost",
        "Infrastructure cost",
        "estimated",
        display,
        f"{source.basis} This is the cost after the change, not the bill being paid today.",
        source.confidence,
    )


def _measured(case: DecisionCase, metric_id: str) -> Judgment | None:
    evidence = _evidence_metric(case, metric_id)
    metric = case.metric(metric_id)
    if evidence is None or metric is None or evidence.value is None:
        return None
    if evidence.confidence < 0.75:
        return None
    return Judgment(
        f"current_{metric_id}",
        f"Current {metric.name[:1].lower()}{metric.name[1:]}",
        "known",
        _point(metric.unit, evidence.value),
        f"{evidence.basis} The value is a measurement, not a forecast.",
        evidence.confidence,
    )


def _engineers(case: DecisionCase) -> Judgment | None:
    limit = _limit(case, "headcount")
    if limit is None:
        return None
    evidence = next((item for item in case.evidence if item.kind == "constraint"), None)
    noun = "engineer" if limit == 1 else "engineers"
    display = f"{plain(limit)} {noun}"
    if evidence is not None and evidence.confidence >= 0.75:
        return Judgment(
            "engineers",
            "Engineers available",
            "known",
            display,
            f"{_basis(evidence)} This is the team on record, not a forecast.",
            evidence.confidence,
        )
    return Judgment(
        "engineers",
        "Engineers available",
        "assumed",
        display,
        "The headcount is a constraint on the request. No staffing record backs it.",
    )


def _timeline(case: DecisionCase) -> Judgment | None:
    limit = _limit(case, "timeline")
    if limit is None:
        return None
    unit = "week" if limit == 1 else "weeks"
    return Judgment(
        "timeline",
        "Timeline limit",
        "assumed",
        f"{plain(limit)} {unit}",
        "The limit was set on the request. Nothing in the evidence measures it.",
    )


def _labor() -> Judgment:
    return Judgment(
        "labor",
        "Labor cost",
        "unknown",
        "Unknown",
        "No labor rate is on record, so engineering time is not converted into dollars.",
    )


def _annual_benefit(case: DecisionCase, chosen: Option | None) -> float | None:
    if chosen is None:
        return None
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if baseline is None:
        return None
    current = _band(baseline, "infra_cost")
    future = _band(chosen, "infra_cost")
    if current is None or future is None:
        return None
    return (current[1] - future[1]) * 12


def _estimate_confidence(case: DecisionCase, option_key: str) -> "_Source | None":
    linked = [item for item in case.evidence if item.option_key == option_key]
    estimates = [item for item in linked if item.kind == "estimate"]
    pool = estimates or linked
    if not pool:
        return None
    evidence = min(pool, key=lambda item: item.confidence)
    return _Source(evidence.confidence, _basis(evidence))


def _evidence_metric(case: DecisionCase, metric_id: str) -> "_Source | None":
    for item in case.evidence:
        if item.metric_id == metric_id and item.value is not None and item.option_key is None:
            return _Source(item.confidence, _basis(item), item.value)
    return None


def _band(option: Option, metric_id: str) -> tuple[float, float, float] | None:
    for item in option.projections:
        if item.metric_id == metric_id:
            return item.p10, item.p50, item.p90
    return None


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _point(unit: str, value: float) -> str:
    if unit == "USD/month":
        return f"${value:,.0f} per month"
    if unit == "minutes":
        noun = "minute" if abs(value - 1) < 1e-9 else "minutes"
        return f"{plain(value)} {noun}"
    if unit == "weeks":
        noun = "week" if abs(value - 1) < 1e-9 else "weeks"
        return f"{plain(value)} {noun}"
    return plain(value)


def _basis(evidence: Evidence) -> str:
    return f"{evidence.source}, confidence {evidence.confidence:.2f}."


class _Source:
    def __init__(self, confidence: float, basis: str, value: float | None = None) -> None:
        self.confidence = confidence
        self.basis = basis
        self.value = value

    @property
    def percent(self) -> str:
        return f"{round(self.confidence * 100)}%"

    @property
    def stance(self) -> str:
        return "known" if self.confidence >= 0.75 else "estimated"
