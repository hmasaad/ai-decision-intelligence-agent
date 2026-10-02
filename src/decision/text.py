"""Plain-language rendering for frames, amounts, and counts."""

import re

from decision.models import DecisionCase, MetricSpec


def plain(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def format_span(metric: MetricSpec, low: float, high: float) -> str:
    if metric.unit == "USD/month":
        return f"${low:,.0f}–${high:,.0f} per month"
    if metric.unit == "minutes":
        return f"{plain(low)}–{plain(high)} minutes"
    if metric.unit == "incidents/quarter":
        return f"{plain(low)}–{plain(high)} per quarter"
    if metric.unit == "weeks":
        return f"{plain(low)}–{plain(high)} weeks"
    if metric.unit:
        return f"{plain(low)}–{plain(high)} {metric.unit}"
    return f"{plain(low)}–{plain(high)}"


def format_amount(metric: MetricSpec, value: float) -> str:
    number = plain(value)
    if metric.unit == "USD/month":
        return f"${value:,.0f} per month"
    if metric.unit == "minutes":
        unit = "minute" if number == "1" else "minutes"
        return f"{number} {unit}"
    if metric.unit == "incidents/quarter":
        unit = "incident" if number == "1" else "incidents"
        return f"{number} {unit} per quarter"
    if metric.unit == "weeks":
        unit = "week" if number == "1" else "weeks"
        return f"{number} {unit}"
    if metric.unit:
        return f"{number} {metric.unit}"
    return number


def render_frame(case: DecisionCase) -> str:
    options = "\n".join(f"{item.key}. {item.name}" for item in case.options) or "Not stated."
    constraints = "\n".join(f"- {item.statement}" for item in case.constraints) or "- Not stated."
    metrics = "\n".join(f"- {item.name}" for item in case.metrics) or "- Not stated."
    objective = case.objective.strip() or "Not stated."
    decision = case.decision or "Not stated."
    return (
        f"Decision:\n{decision}\n\n"
        f"Objective:\n{objective}\n\n"
        f"Options:\n{options}\n\n"
        f"Constraints:\n{constraints}\n\n"
        f"Success metrics:\n{metrics}\n"
    )


def slug(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"", "x", "service x", "this service"}:
        return "service-x"
    cleaned = re.sub(r"^the\s+", "", lowered)
    cleaned = re.sub(r"\s+service$", "", cleaned)
    token = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return token or "decision"
