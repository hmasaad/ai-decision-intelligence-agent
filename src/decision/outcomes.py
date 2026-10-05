"""What was predicted, what happened, and what to carry forward.

Cost, timeline, and return are read from the option that was executed.
The return is the annual infrastructure benefit. It is inferred from the
bill, not measured as a separate figure. Labor stays unknown.
"""

from decision.learn import _variance, executed_option
from decision.models import DecisionCase, MetricSpec, Option, Outcome
from decision.text import format_amount


class ScoreRow:
    def __init__(
        self,
        label: str,
        expected: str,
        actual: str,
        variance: str,
        why: str = "",
        learning: str = "",
    ) -> None:
        self.label = label
        self.expected = expected
        self.actual = actual
        self.variance = variance
        self.why = why
        self.learning = learning


def build_scorecard(case: DecisionCase) -> list[ScoreRow]:
    option = executed_option(case)
    if option is None:
        return []
    cost = case.metric("infra_cost")
    timeline = _timeline_metric(case)
    rows: list[ScoreRow] = []
    if cost is not None:
        rows.append(_measured(case, option, cost, "Cost"))
    if timeline is not None:
        rows.append(_measured(case, option, timeline, "Timeline"))
    roi = _roi(case, option)
    if roi is not None:
        rows.append(roi)
    return rows


def render_scorecard(case: DecisionCase) -> str:
    rows = build_scorecard(case)
    if not rows:
        return "Nothing is estimated yet, so there is no outcome to compare.\n"
    lines = ["Expected", ""]
    width = max(len(row.label) for row in rows)
    for row in rows:
        lines.append(f"{row.label:<{width}}  {row.expected}")
    lines.extend(["", "Actual", ""])
    for row in rows:
        lines.append(f"{row.label:<{width}}  {row.actual}")
    if any(row.why for row in rows):
        lines.append("")
        for row in rows:
            if not row.why:
                continue
            lines.extend(
                [
                    row.label,
                    "Prediction",
                    row.expected,
                    "↓",
                    "Actual",
                    row.actual,
                    "↓",
                    "Variance",
                    row.variance,
                    "↓",
                    "Why?",
                    row.why,
                    "↓",
                    "Learning",
                    row.learning,
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _measured(case: DecisionCase, option: Option, metric: MetricSpec, label: str) -> ScoreRow:
    predicted = _p50(option, metric.id)
    expected = format_amount(metric, predicted) if predicted is not None else "Not on record."
    outcome = _outcome(case, metric.id)
    if outcome is None or predicted is None:
        return ScoreRow(label, expected, "Not recorded.", "Not recorded.")
    return ScoreRow(
        label,
        format_amount(metric, outcome.predicted),
        format_amount(metric, outcome.actual),
        outcome.variance,
        outcome.cause,
        outcome.learning,
    )


def _roi(case: DecisionCase, option: Option) -> ScoreRow | None:
    baseline = _baseline_monthly(case)
    expected_cost = _p50(option, "infra_cost")
    if baseline is None or expected_cost is None:
        return None
    expected = (baseline - expected_cost) * 12
    outcome = _outcome(case, "infra_cost")
    expected_text = _benefit(expected)
    if outcome is None:
        return ScoreRow("ROI", expected_text, "Not recorded.", "Not recorded.")
    actual = (baseline - outcome.actual) * 12
    gap = (expected - actual) / abs(expected) if abs(expected) > 1e-9 else 0.0
    return ScoreRow(
        "ROI",
        expected_text,
        _benefit(actual),
        _variance(actual, expected),
        _roi_why(baseline, expected_cost, outcome.actual),
        _roi_learning(expected, actual, gap),
    )


def _roi_why(baseline: float, expected_cost: float, actual_cost: float) -> str:
    return (
        "Inferred from the infrastructure bill. "
        f"Today's service is ${baseline:,.0f} per month. "
        f"The expected bill after the change was ${expected_cost:,.0f} per month. "
        f"The recorded bill is ${actual_cost:,.0f} per month."
    )


def _roi_learning(expected: float, actual: float, gap: float) -> str:
    if gap > 0.1:
        return (
            "Future estimates of the annual benefit should start from "
            f"{_benefit(actual)}, not {_benefit(expected)}."
        )
    if gap < -0.1:
        return f"Future estimates of the annual benefit can start from {_benefit(actual)}."
    if abs(actual - expected) >= 1:
        return (
            f"The return moved from {_benefit(expected)} to {_benefit(actual)}. "
            "That stays inside 10%, so the expected return holds."
        )
    return "No revision. The expected return held."


def _benefit(value: float) -> str:
    if abs(value) < 1:
        return "No change"
    kind = "benefit" if value > 0 else "loss"
    return f"${abs(value):,.0f} {kind}"


def _timeline_metric(case: DecisionCase) -> MetricSpec | None:
    for metric in case.metrics:
        if metric.binds == "timeline" or metric.id == "effort":
            return metric
    return None


def _outcome(case: DecisionCase, metric_id: str) -> Outcome | None:
    for item in case.outcomes:
        if item.metric_id == metric_id:
            return item
    return None


def _p50(option: Option, metric_id: str) -> float | None:
    for item in option.projections:
        if item.metric_id == metric_id:
            return item.p50
    return None


def _baseline_monthly(case: DecisionCase) -> float | None:
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if baseline is None:
        return None
    return _p50(baseline, "infra_cost")

