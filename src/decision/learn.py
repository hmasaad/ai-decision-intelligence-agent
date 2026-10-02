"""Compare the outcome with the estimate and write the lesson."""

from decision.models import DecisionCase, Evidence, Lesson, Option, Outcome, Prior
from decision.text import format_amount, format_span, plain


def worse_by(actual: float, predicted: float, direction: str) -> float:
    base = abs(predicted) if abs(predicted) > 1e-9 else 1.0
    if direction == "lower":
        return (actual - predicted) / base
    return (predicted - actual) / base


def build_outcomes(case: DecisionCase, actuals: dict[str, float]) -> list[Outcome]:
    if case.brief is None or case.brief.recommendation_key is None:
        return []
    option = case.option(case.brief.recommendation_key)
    if option is None:
        return []
    outcomes: list[Outcome] = []
    for metric in case.metrics:
        predicted = next(
            (item.p50 for item in option.projections if item.metric_id == metric.id),
            None,
        )
        if predicted is None or metric.id not in actuals:
            continue
        actual = actuals[metric.id]
        gap = worse_by(actual, predicted, metric.direction)
        outcomes.append(
            Outcome(
                metric_id=metric.id,
                actual=actual,
                predicted=predicted,
                worse_by=gap,
                variance=_variance(actual, predicted),
                cause=_cause(case, option, metric.id, actual, predicted),
                learning=_learning(metric.name, actual, predicted, gap, metric),
            )
        )
    return outcomes


def write_lesson(case: DecisionCase) -> Lesson:
    statements: list[str] = []
    revisions: list[str] = []
    signed: list[float] = []
    reevaluate = False
    reasons: list[str] = []
    for outcome in case.outcomes:
        metric = case.metric(outcome.metric_id)
        if metric is None:
            continue
        signed.append(outcome.worse_by)
        actual = format_amount(metric, outcome.actual)
        predicted = format_amount(metric, outcome.predicted)
        if abs(outcome.worse_by) < 0.01:
            statements.append(f"{metric.name} matched the expected case ({actual}).")
            continue
        if abs(outcome.worse_by) < 0.1:
            statements.append(
                f"{metric.name} stayed within 10% of the expected case ({actual} vs {predicted})."
            )
            continue
        percent = round(abs(outcome.worse_by) * 100)
        word = "worse" if outcome.worse_by > 0 else "better"
        statements.append(
            f"{metric.name} came in {percent}% {word} than the expected case ({actual} vs {predicted})."
        )
        if outcome.worse_by > 0:
            revisions.append(
                f"Next time, expect {metric.name.lower()} of {actual}, not {predicted}."
            )
        if outcome.worse_by >= 0.25 and metric.weight >= 1.5:
            reevaluate = True
            reasons.append(
                f"{metric.name} missed the expected case by {percent}%."
            )
    constraint_note = _constraint_note(case)
    if constraint_note:
        statements.append(constraint_note)
        if "broke" in constraint_note:
            reevaluate = True
            reasons.append(constraint_note)
    bias = _bias(signed)
    if reevaluate:
        reason = " ".join(reasons) + " Revise the estimate before trusting this pattern on the next decision."
    elif bias == "calibrated":
        reason = "The expected case held. The same estimates can be reused."
    else:
        reason = f"The estimate was {bias}. Carry the revision into the next decision of this pattern."
    if not reevaluate and bias == "optimistic":
        reason = (
            "The estimate was optimistic. Carry the revised numbers into the next decision. "
            "This one still finished inside the constraints."
        )
    text = "\n".join(statements + revisions + [reason])
    return Lesson(
        bias=bias,
        reevaluate=reevaluate,
        reason=reason,
        statements=statements,
        revisions=revisions,
        text=text,
    )


def priors_from(case: DecisionCase) -> list[Prior]:
    if case.lesson is None:
        return []
    priors: list[Prior] = []
    subject = case.subject or "the last decision"
    for outcome in case.outcomes:
        if abs(outcome.worse_by) < 0.1:
            continue
        metric = case.metric(outcome.metric_id)
        if metric is None or outcome.worse_by <= 0:
            continue
        percent = round(outcome.worse_by * 100)
        actual = format_amount(metric, outcome.actual)
        predicted = format_amount(metric, outcome.predicted)
        priors.append(
            Prior(
                id=f"{case.id}:{metric.id}",
                pattern=case.pattern,
                metric_id=metric.id,
                metric_name=metric.name,
                factor=outcome.actual / outcome.predicted if outcome.predicted else 1,
                statement=(
                    f"On the {subject} decision, {metric.name.lower()} came in {percent}% worse "
                    f"than expected. Use {actual} as the next expected case, not {predicted}."
                ),
                source_id=case.id,
            )
        )
    return priors


def _variance(actual: float, predicted: float) -> str:
    if abs(predicted) < 1e-9:
        return "—"
    change = (actual - predicted) / abs(predicted)
    if abs(change) < 0.005:
        return "0%"
    sign = "+" if change > 0 else "-"
    return f"{sign}{round(abs(change) * 100)}%"


def _learning(name: str, actual: float, predicted: float, gap: float, metric) -> str:
    if gap > 0.1:
        return (
            f"Future estimates of {name.lower()} should start from "
            f"{format_amount(metric, actual)}, not {format_amount(metric, predicted)}."
        )
    if gap < -0.1:
        return (
            f"Future estimates of {name.lower()} can start from {format_amount(metric, actual)}."
        )
    return "No revision. The expected case held."


def _cause(
    case: DecisionCase,
    option: Option,
    metric_id: str,
    actual: float,
    predicted: float,
) -> str:
    metric = case.metric(metric_id)
    if metric is None:
        return "No metric is on record for this result."
    precedent = _precedent(case, metric, actual)
    if precedent is not None:
        return (
            f"The {precedent.source} says a partial migration finished in {format_amount(metric, actual)}. "
            f"This result matched that precedent, not the estimate of {format_amount(metric, predicted)}."
        )
    band = next((item for item in option.projections if item.metric_id == metric_id), None)
    source = _estimate(case, option.key)
    if band is not None and band.p10 <= actual <= band.p90:
        where = f"{format_amount(metric, actual)} is inside the {format_span(metric, band.p10, band.p90)} band."
        if source is None:
            return f"{where} The expected case was an estimate, not a measurement."
        percent = f"{round(source.confidence * 100)}%"
        return (
            f"{where} The expected {format_amount(metric, predicted)} came from {source.source}, "
            f"an estimate at {percent} confidence."
        )
    if band is not None:
        return (
            f"{format_amount(metric, actual)} fell outside the "
            f"{format_span(metric, band.p10, band.p90)} band. The estimate did not cover this outcome."
        )
    return "The expected case was a projection, and this result moved off it."


def _precedent(case: DecisionCase, metric, actual: float) -> Evidence | None:
    needle = f"{plain(actual)} {metric.unit.split('/')[0]}"
    weeks = f"{plain(actual)} week"
    for item in case.evidence:
        if item.kind != "precedent":
            continue
        text = item.statement.lower()
        if weeks in text or needle.lower() in text:
            return item
    return None


def _estimate(case: DecisionCase, option_key: str) -> Evidence | None:
    estimates = [
        item for item in case.evidence if item.option_key == option_key and item.kind == "estimate"
    ]
    if not estimates:
        return None
    return min(estimates, key=lambda item: item.confidence)


def _bias(signed: list[float]) -> str:
    if not signed:
        return "calibrated"
    mean = sum(signed) / len(signed)
    if mean > 0.1:
        return "optimistic"
    if mean < -0.1:
        return "pessimistic"
    return "calibrated"


def _constraint_note(case: DecisionCase) -> str:
    timeline = next((item for item in case.constraints if item.kind == "timeline"), None)
    effort = next((item for item in case.outcomes if item.metric_id == "effort"), None)
    if timeline is None or timeline.limit is None or effort is None:
        return ""
    if effort.actual > timeline.limit:
        return (
            f"Engineering effort of {plain(effort.actual)} weeks broke the "
            f"{plain(timeline.limit)}-week timeline."
        )
    return (
        f"Engineering effort of {plain(effort.actual)} weeks stayed inside the "
        f"{plain(timeline.limit)}-week timeline."
    )
