"""Scenario simulation: three cases per option, scored against the constraints."""

from decision.models import Band, DecisionCase, MetricSpec, Option, Projection, Scenario
from decision.text import format_amount, plain


def is_modeled(case: DecisionCase) -> bool:
    if len(case.options) < 2 or not case.metrics or not case.objective.strip():
        return False
    needed = {metric.id for metric in case.metrics}
    for option in case.options:
        if option.engineers is None or option.weeks is None or option.requires_downtime is None:
            return False
        found = {item.metric_id for item in option.projections}
        if not needed <= found:
            return False
    return True


def projection(option: Option, metric_id: str) -> Projection | None:
    for item in option.projections:
        if item.metric_id == metric_id:
            return item
    return None


BASE_CASES = ("optimistic", "expected", "pessimistic")
STRESS_CASES = (
    "dependency_failure",
    "resource_shortage",
    "timeline_slippage",
    "unexpected_cost",
)
CASE_LABELS = {
    "optimistic": "Best case",
    "expected": "Expected",
    "pessimistic": "Worst case",
    "dependency_failure": "Dependency failure",
    "resource_shortage": "Resource shortage",
    "timeline_slippage": "Timeline slippage",
    "unexpected_cost": "Unexpected cost",
}


def scenario_value(item: Projection, direction: str, name: str) -> float:
    if name == "expected":
        return item.p50
    worse = name == "pessimistic"
    if direction == "lower":
        return item.p90 if worse else item.p10
    return item.p10 if worse else item.p90


def _anchors(case: DecisionCase) -> dict[str, tuple[float, float]]:
    anchors: dict[str, tuple[float, float]] = {}
    for metric in case.metrics:
        values: list[float] = []
        for option in case.options:
            item = projection(option, metric.id)
            if item is not None:
                values.extend([item.p10, item.p50, item.p90])
        if not values:
            continue
        if metric.direction == "lower":
            anchors[metric.id] = (min(values), max(values))
        else:
            anchors[metric.id] = (max(values), min(values))
    return anchors


def _score(case: DecisionCase, values: dict[str, float], anchors: dict[str, tuple[float, float]]) -> float:
    weighted = 0.0
    weight = 0.0
    for metric in case.metrics:
        if metric.id not in values or metric.id not in anchors:
            continue
        best, worst = anchors[metric.id]
        if metric.direction == "lower":
            span = worst - best
            points = 1.0 if span == 0 else (worst - values[metric.id]) / span
        else:
            span = best - worst
            points = 1.0 if span == 0 else (values[metric.id] - worst) / span
        weighted += metric.weight * points
        weight += metric.weight
    if weight == 0:
        return 0.0
    return weighted / weight


def _bound_weeks(case: DecisionCase, option: Option, values: dict[str, float]) -> float | None:
    for metric in case.metrics:
        if metric.binds == "timeline" and metric.id in values:
            return values[metric.id]
    return option.weeks


def blocks(
    case: DecisionCase,
    option: Option,
    values: dict[str, float],
    engineers: float | None = None,
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    codes: list[str] = []
    needed = option.engineers if engineers is None else engineers
    for constraint in case.constraints:
        if constraint.kind == "headcount":
            if needed is None:
                reasons.append("Engineer count is not set.")
                codes.append("headcount")
            elif constraint.limit is not None and needed > constraint.limit:
                reasons.append(
                    f"Needs {plain(needed)} engineers and {plain(constraint.limit)} are available."
                )
                codes.append("headcount")
        elif constraint.kind == "timeline":
            weeks = _bound_weeks(case, option, values)
            if weeks is None:
                reasons.append("Timeline is not set.")
                codes.append("timeline")
            elif constraint.limit is not None and weeks > constraint.limit:
                reasons.append(
                    f"Needs {plain(weeks)} weeks and the limit is {plain(constraint.limit)} weeks."
                )
                codes.append("timeline")
        elif constraint.kind == "downtime" and constraint.limit == 0:
            if option.requires_downtime is None:
                reasons.append("Downtime is not set.")
                codes.append("downtime")
            elif option.requires_downtime:
                reasons.append("Requires production downtime.")
                codes.append("downtime")
    return reasons, codes


def _values(case: DecisionCase, option: Option, name: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for metric in case.metrics:
        item = projection(option, metric.id)
        if item is not None:
            values[metric.id] = scenario_value(item, metric.direction, name)
    return values


def build_scenarios(case: DecisionCase) -> list[Scenario]:
    anchors = _anchors(case)
    baseline = _baseline_values(case)
    scenarios: list[Scenario] = []
    for option in case.options:
        expected_values: dict[str, float] = {}
        for name in BASE_CASES:
            values = _values(case, option, name)
            if name == "expected":
                expected_values = values
            scenarios.append(_scenario(case, option, name, values, anchors, baseline))
        for name in STRESS_CASES:
            values = _stress(option, name, expected_values, baseline)
            engineers = _stress_engineers(option, name)
            scenarios.append(
                _scenario(case, option, name, values, anchors, baseline, engineers=engineers)
            )
    return scenarios


def _baseline_values(case: DecisionCase) -> dict[str, float]:
    baseline = next((option for option in case.options if option.role == "status_quo"), None)
    if baseline is None and case.options:
        baseline = case.options[0]
    if baseline is None:
        return {}
    return _values(case, baseline, "expected")


def _stress(
    option: Option,
    name: str,
    expected: dict[str, float],
    baseline: dict[str, float],
) -> dict[str, float]:
    values = dict(expected)
    if name == "dependency_failure":
        for metric_id in ("deploy_time", "incident_rate"):
            if metric_id in values and metric_id in baseline:
                values[metric_id] = (values[metric_id] + baseline[metric_id]) / 2
        if "effort" in values:
            values["effort"] = values["effort"] * 1.25
    elif name == "resource_shortage" and "effort" in values:
        values["effort"] = values["effort"] * 1.5
    elif name == "timeline_slippage" and "effort" in values:
        values["effort"] = values["effort"] * 1.5
    elif name == "unexpected_cost" and "infra_cost" in values:
        values["infra_cost"] = values["infra_cost"] * 1.5
    return values


def _stress_engineers(option: Option, name: str) -> float | None:
    if name != "resource_shortage" or not option.engineers:
        return None
    return option.engineers + 1


def _scenario(
    case: DecisionCase,
    option: Option,
    name: str,
    values: dict[str, float],
    anchors: dict[str, tuple[float, float]],
    baseline: dict[str, float],
    engineers: float | None = None,
) -> Scenario:
    reasons, codes = blocks(case, option, values, engineers)
    benefit = _annual_benefit(values, baseline)
    headline, kind = _headline(benefit)
    return Scenario(
        option_key=option.key,
        name=name,
        label=CASE_LABELS[name],
        values=values,
        feasible=not reasons,
        blocked_by=reasons,
        block_codes=codes,
        score=_score(case, values, anchors),
        headline=headline,
        detail=_detail(case, option, name, values, reasons, kind),
    )


def _annual_benefit(values: dict[str, float], baseline: dict[str, float]) -> float | None:
    if "infra_cost" not in values or "infra_cost" not in baseline:
        return None
    return (baseline["infra_cost"] - values["infra_cost"]) * 12


def _headline(benefit: float | None) -> tuple[str, str]:
    if benefit is None or abs(benefit) < 1:
        return "No change", "unchanged"
    kind = "benefit" if benefit > 0 else "loss"
    return f"${abs(benefit):,.0f} {kind}", kind


def _detail(
    case: DecisionCase,
    option: Option,
    name: str,
    values: dict[str, float],
    reasons: list[str],
    kind: str,
) -> str:
    shortage = "The team is one engineer short, and the work takes 50% longer."
    if name == "resource_shortage" and not option.engineers:
        shortage = "Doing nothing needs no extra engineer, so the shortage does not add demand."
    money = {
        "optimistic": "Infrastructure savings against doing nothing, at the optimistic estimate.",
        "expected": "Infrastructure savings against doing nothing, at the expected estimate.",
        "pessimistic": "Infrastructure savings against doing nothing, at the pessimistic estimate.",
        "dependency_failure": "A dependency misses, so deploy time and incidents move halfway back toward today and the work runs 25% longer.",
        "resource_shortage": shortage,
        "timeline_slippage": "The work takes 50% longer than the expected case.",
        "unexpected_cost": "Infrastructure cost runs 50% above the expected case.",
    }[name]
    deploy = _metric_phrase(case, "deploy_time", values)
    effort = _metric_phrase(case, "effort", values)
    parts = [money]
    if deploy:
        parts.append(f"Deploy time is {deploy}.")
    if effort and name != "expected":
        parts.append(f"Engineering effort is {effort}.")
    if kind == "loss":
        parts.append("This costs more than doing nothing.")
    if reasons:
        parts.append(" ".join(reasons))
    return " ".join(parts)


def _metric_phrase(case: DecisionCase, metric_id: str, values: dict[str, float]) -> str:
    metric = case.metric(metric_id)
    if metric is None or metric_id not in values:
        return ""
    return format_amount(metric, values[metric_id])


def recommend(case: DecisionCase, scenarios: list[Scenario]) -> str | None:
    feasible = [item for item in scenarios if item.name == "expected" and item.feasible]
    if not feasible:
        return None

    def sort_key(item: Scenario) -> tuple[float, float, str]:
        option = case.option(item.option_key)
        weeks = option.weeks if option and option.weeks is not None else 0
        return (item.score, -weeks, item.option_key)

    return max(feasible, key=sort_key).option_key


def build_bands(case: DecisionCase) -> list[Band]:
    bands: list[Band] = []
    for option in case.options:
        for metric in case.metrics:
            item = projection(option, metric.id)
            if item is None:
                continue
            base = abs(item.p50) if abs(item.p50) > 1e-9 else 1.0
            bands.append(
                Band(
                    option_key=option.key,
                    metric_id=metric.id,
                    low=item.p10,
                    mid=item.p50,
                    high=item.p90,
                    spread=(item.p90 - item.p10) / base,
                )
            )
    return bands


def metric_by_id(case: DecisionCase) -> dict[str, MetricSpec]:
    return {item.id: item for item in case.metrics}
