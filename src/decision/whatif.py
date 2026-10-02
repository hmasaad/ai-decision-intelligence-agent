"""Ask what happens when one assumption changes.

A change in capacity stretches the timeline. A longer timeline means more
weeks on today's infrastructure bill, a shorter first year of savings, and
a lower confidence, because the new timeline was not measured.
"""

from decision.models import Constraint, DecisionCase
from decision.simulate import build_scenarios, recommend
from decision.text import plain
from decision.uncertainty import return_confidence

DERIVED_CONFIDENCE = 0.85
OVERRIDDEN_BAN = 0.75


class WhatIfStep:
    def __init__(self, label: str, before: str, after: str, note: str = "") -> None:
        self.label = label
        self.before = before
        self.after = after
        self.note = note


class WhatIf:
    def __init__(
        self,
        question: str,
        steps: list[WhatIfStep],
        recommendation_before: str,
        recommendation_after: str,
        changed: bool,
        from_engineers: float | None,
        engineers: float | None,
        from_weeks: float | None,
        weeks: float | None,
        downtime: str,
    ) -> None:
        self.question = question
        self.steps = steps
        self.recommendation_before = recommendation_before
        self.recommendation_after = recommendation_after
        self.changed = changed
        self.from_engineers = from_engineers
        self.engineers = engineers
        self.from_weeks = from_weeks
        self.weeks = weeks
        self.downtime = downtime


def posed(case: DecisionCase) -> WhatIf | None:
    """The question the decision is already sitting on."""

    if not case.scenarios:
        return None
    available = _limit(case, "headcount")
    weeks = _limit(case, "timeline")
    if available is None or weeks is None:
        return None
    fuller = [option.engineers for option in case.options if option.engineers and option.engineers > available]
    assumed = max(fuller) if fuller else available
    return answer(case, engineers=available, from_engineers=assumed, from_weeks=weeks)


def opening(case: DecisionCase) -> str | None:
    """A link that asks the question which would let a blocked option win."""

    if not case.scenarios:
        return None
    key = recommend(case, case.scenarios)
    chosen = case.scenario(key, "expected") if key else None
    if chosen is None:
        return None
    candidate = None
    for option in case.options:
        expected = case.scenario(option.key, "expected")
        if expected is None or expected.feasible or option.key == key:
            continue
        if expected.score <= chosen.score + 0.01:
            continue
        if candidate is None or expected.score > candidate[0]:
            candidate = (expected.score, option)
    if candidate is None:
        return None
    option = candidate[1]
    available = _limit(case, "headcount")
    weeks = _limit(case, "timeline")
    params = [
        f"from_engineers={plain(available)}" if available is not None else "",
        f"engineers={plain(option.engineers)}" if option.engineers is not None else "",
        f"from_weeks={plain(weeks)}" if weeks is not None else "",
        f"weeks={plain(option.weeks)}" if option.weeks is not None else "",
    ]
    if option.requires_downtime:
        params.append("downtime=allow")
    return "&".join(part for part in params if part)


def answer(
    case: DecisionCase,
    *,
    engineers: float | None = None,
    from_engineers: float | None = None,
    weeks: float | None = None,
    from_weeks: float | None = None,
    downtime_forbidden: bool | None = None,
) -> WhatIf | None:
    if not case.scenarios:
        return None
    current_engineers = _limit(case, "headcount")
    current_weeks = _limit(case, "timeline")
    from_e = current_engineers if from_engineers is None else from_engineers
    to_e = current_engineers if engineers is None else engineers
    from_w = current_weeks if from_weeks is None else from_weeks
    derived = False
    if weeks is None and from_w is not None and from_e and to_e and to_e != from_e:
        to_w = float(round(from_w * from_e / to_e))
        derived = True
    else:
        to_w = from_w if weeks is None else weeks

    before_key = _recommend(case, from_e, from_w, None)
    after_key = _recommend(case, to_e, to_w, downtime_forbidden)
    before_conf = return_confidence(case, before_key)
    after_conf = return_confidence(case, after_key)
    reasons: list[str] = []
    if after_conf is not None and to_w is not None and current_weeks is not None and to_w != current_weeks:
        after_conf *= DERIVED_CONFIDENCE
        reasons.append(f"the {plain(to_w)}-week timeline is assumed")
    if downtime_forbidden is False and _downtime_forbidden(case):
        if after_conf is not None:
            after_conf *= OVERRIDDEN_BAN
        reasons.append("this sets aside the recorded downtime ban")

    steps = [
        _capacity_step(from_e, to_e),
        _timeline_step(from_w, to_w, from_e, to_e, derived),
        _cost_step(case, from_w, to_w),
        _return_step(case, before_key, after_key, from_w, to_w),
        _confidence_step(before_conf, after_conf, reasons),
    ]
    question = _question(from_e, to_e, from_w, to_w, downtime_forbidden, derived)
    downtime = "keep" if downtime_forbidden is None else "forbid" if downtime_forbidden else "allow"
    return WhatIf(
        question=question,
        steps=steps,
        recommendation_before=_option_name(case, before_key),
        recommendation_after=_option_name(case, after_key),
        changed=before_key != after_key,
        from_engineers=from_e,
        engineers=to_e,
        from_weeks=from_w,
        weeks=to_w,
        downtime=downtime,
    )


def render_whatif(item: WhatIf) -> str:
    lines = [item.question, ""]
    for step in item.steps:
        lines.append(step.label)
        lines.append(f"{step.before} → {step.after}")
        if step.note:
            lines.append(step.note)
        lines.append("")
    change = "changes" if item.changed else "stays"
    lines.append(
        f"Recommendation {change}: {item.recommendation_before} → {item.recommendation_after}"
    )
    return "\n".join(lines) + "\n"


def _recommend(
    case: DecisionCase,
    engineers: float | None,
    weeks: float | None,
    downtime_forbidden: bool | None,
) -> str | None:
    updated = _with_constraints(case, engineers, weeks, downtime_forbidden)
    return recommend(updated, build_scenarios(updated))


def _with_constraints(
    case: DecisionCase,
    engineers: float | None,
    weeks: float | None,
    downtime_forbidden: bool | None,
) -> DecisionCase:
    constraints: list[Constraint] = []
    for item in case.constraints:
        if item.kind == "headcount" and engineers is not None:
            noun = "engineer" if engineers == 1 else "engineers"
            constraints.append(
                item.model_copy(
                    update={"limit": engineers, "statement": f"{plain(engineers)} {noun} available"}
                )
            )
        elif item.kind == "timeline" and weeks is not None:
            constraints.append(
                item.model_copy(
                    update={"limit": weeks, "statement": f"{plain(weeks)}-week timeline"}
                )
            )
        elif item.kind == "downtime" and downtime_forbidden is not None:
            if downtime_forbidden:
                constraints.append(
                    item.model_copy(update={"limit": 0, "statement": "No production downtime"})
                )
            else:
                constraints.append(
                    item.model_copy(update={"limit": 1, "statement": "Production downtime is allowed"})
                )
        else:
            constraints.append(item)
    return case.model_copy(update={"constraints": constraints})


def _capacity_step(before: float | None, after: float | None) -> WhatIfStep:
    return WhatIfStep(
        "Engineering capacity",
        _engineers(before),
        _engineers(after),
        "Capacity is the assumption this question changes.",
    )


def _timeline_step(
    before: float | None,
    after: float | None,
    from_engineers: float | None,
    to_engineers: float | None,
    derived: bool,
) -> WhatIfStep:
    note = "The timeline limit on the decision."
    if before != after:
        note = "Set for this question. The new length is assumed, not measured."
    if derived and before is not None and from_engineers and to_engineers:
        note = (
            f"{plain(before)} × {plain(from_engineers)} ÷ {plain(to_engineers)} "
            f"rounds to {plain(after)} weeks. The stretch is assumed, not estimated."
        )
    return WhatIfStep("Timeline", _weeks(before), _weeks(after), note)


def _cost_step(case: DecisionCase, before: float | None, after: float | None) -> WhatIfStep:
    monthly = _current_monthly(case)
    if monthly is None or before is None or after is None:
        return WhatIfStep("Migration cost", "Unknown", "Unknown", "Today's infrastructure bill is not on record.")
    earlier = _program_cost(monthly, before)
    later = _program_cost(monthly, after)
    movement = "increases" if later > earlier + 1 else "decreases" if earlier > later + 1 else "stays put"
    return WhatIfStep(
        "Migration cost",
        _dollars(earlier),
        _dollars(later),
        (
            f"The cost {movement}. It is today's ${monthly:,.0f} per month bill for the length of the work, "
            "inferred from a known cost and an assumed timeline. Labor is still unknown."
        ),
    )


def _return_step(
    case: DecisionCase,
    before_key: str | None,
    after_key: str | None,
    before_weeks: float | None,
    after_weeks: float | None,
) -> WhatIfStep:
    earlier = _first_year(case, before_key, before_weeks)
    later = _first_year(case, after_key, after_weeks)
    earlier_text = "Unknown" if earlier is None else _signed(earlier)
    later_text = "Unknown" if later is None else _signed(later)
    note = _return_note(case, before_key, after_key, earlier, later)
    return WhatIfStep("Expected return", earlier_text, later_text, note)


def _return_note(
    case: DecisionCase,
    before_key: str | None,
    after_key: str | None,
    earlier: float | None,
    later: float | None,
) -> str:
    annual = _annual(case, after_key)
    annual_text = ""
    if annual is not None:
        annual_text = f" The annual run-rate is {_signed(annual)}."
    if earlier is None or later is None:
        return "The first-year return needs an infrastructure estimate." + annual_text
    if later < earlier - 1:
        movement = "decreases"
    elif later > earlier + 1:
        movement = "increases"
    else:
        movement = "stays put"
    call = ""
    if before_key != after_key:
        call = f" The recommendation moves to {_option_name(case, after_key)}."
    return (
        f"The first-year return {movement}, because savings start when the timeline ends."
        + call
        + annual_text
        + " This figure is inferred."
    )


def _confidence_step(before: float | None, after: float | None, reasons: list[str]) -> WhatIfStep:
    if before is None or after is None:
        return WhatIfStep(
            "Decision confidence",
            "—" if before is None else _percent(before),
            "—" if after is None else _percent(after),
            "Confidence stays blank where a source is missing.",
        )
    if reasons:
        note = "The expected return rests on an estimated cost. " + _sentence(reasons) + "."
    elif abs(after - before) < 0.005:
        note = "The sources behind the return did not change."
    else:
        note = "The winning option brings a different source confidence."
    return WhatIfStep("Decision confidence", _percent(before), _percent(after), note)


def _question(
    from_e: float | None,
    to_e: float | None,
    from_w: float | None,
    to_w: float | None,
    downtime_forbidden: bool | None,
    derived: bool,
) -> str:
    parts: list[str] = []
    if from_e is not None and to_e is not None and from_e != to_e:
        parts.append(f"engineering capacity changes from {plain(from_e)} to {plain(to_e)}")
    if not derived and from_w is not None and to_w is not None and from_w != to_w:
        parts.append(f"the timeline changes from {plain(from_w)} to {plain(to_w)} weeks")
    if downtime_forbidden is False:
        parts.append("production downtime is allowed")
    elif downtime_forbidden is True:
        parts.append("production downtime is forbidden")
    if not parts:
        return "What happens if this assumption stays as it is?"
    return "What happens if " + _join(parts) + "?"


def _first_year(case: DecisionCase, key: str | None, weeks: float | None) -> float | None:
    if key is None or weeks is None:
        return None
    monthly = _monthly_savings(case, key)
    if monthly is None:
        return None
    remaining = max(0.0, 12 - weeks * 12 / 52)
    return monthly * remaining


def _annual(case: DecisionCase, key: str | None) -> float | None:
    monthly = _monthly_savings(case, key)
    if monthly is None:
        return None
    return monthly * 12


def _monthly_savings(case: DecisionCase, key: str | None) -> float | None:
    option = case.option(key) if key else None
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if option is None or baseline is None:
        return None
    current = _projection(baseline, "infra_cost")
    future = _projection(option, "infra_cost")
    if current is None or future is None:
        return None
    return current - future


def _current_monthly(case: DecisionCase) -> float | None:
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if baseline is None:
        return None
    return _projection(baseline, "infra_cost")


def _projection(option, metric_id: str) -> float | None:
    for item in option.projections:
        if item.metric_id == metric_id:
            return item.p50
    return None


def _program_cost(monthly: float, weeks: float) -> float:
    return monthly * weeks * 12 / 52


def _option_name(case: DecisionCase, key: str | None) -> str:
    if key is None:
        return "No feasible option"
    option = case.option(key)
    if option is None:
        return key
    return f"{option.key}. {option.name}"


def _engineers(value: float | None) -> str:
    if value is None:
        return "Not set"
    noun = "engineer" if value == 1 else "engineers"
    return f"{plain(value)} {noun}"


def _weeks(value: float | None) -> str:
    if value is None:
        return "Not set"
    noun = "week" if value == 1 else "weeks"
    return f"{plain(value)} {noun}"


def _dollars(value: float) -> str:
    return f"${value:,.0f}"


def _signed(value: float) -> str:
    if abs(value) < 1:
        return "No change"
    kind = "benefit" if value > 0 else "loss"
    return f"${abs(value):,.0f} {kind}"


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _sentence(reasons: list[str]) -> str:
    text = _join(reasons)
    return text[:1].upper() + text[1:]


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _downtime_forbidden(case: DecisionCase) -> bool:
    for item in case.constraints:
        if item.kind == "downtime" and item.limit == 0:
            return True
    return False
