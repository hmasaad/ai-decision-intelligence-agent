"""Best, expected, and worst, then what moves when an assumption changes.

The three cases are the stored estimate. The chain is the assumption this
decision is already sitting on. A variable with no record stays blank.
Budget, customer adoption, and market conditions are not invented.
"""

from decision.models import DecisionCase, Option
from decision.text import plain
from decision.whatif import WhatIf, posed

_CASE_NAMES = (
    ("optimistic", "Best case"),
    ("expected", "Expected case"),
    ("pessimistic", "Worst case"),
)


class ScenarioCase:
    def __init__(self, name: str, headline: str, note: str = "") -> None:
        self.name = name
        self.headline = headline
        self.note = note


class ScenarioVariable:
    def __init__(self, name: str, detail: str) -> None:
        self.name = name
        self.detail = detail


class ChainStep:
    def __init__(self, label: str, change: str, note: str = "") -> None:
        self.label = label
        self.change = change
        self.note = note


class ScenarioEngine:
    def __init__(
        self,
        option: str,
        cases: list[ScenarioCase],
        variables: list[ScenarioVariable],
        chain: list[ChainStep],
        reading: str,
    ) -> None:
        self.option = option
        self.cases = cases
        self.variables = variables
        self.chain = chain
        self.reading = reading

    @property
    def ready(self) -> bool:
        return bool(self.chain)


def build_engine(case: DecisionCase) -> ScenarioEngine:
    """The three cases and the assumption-change chain for one decision."""

    chosen = _chosen(case)
    item = posed(case)
    return ScenarioEngine(
        option=f"{chosen.key}. {chosen.name}" if chosen else "Not recommended yet.",
        cases=_cases(case, chosen),
        variables=_variables(case, chosen, item),
        chain=_chain(item) if item is not None else [],
        reading=_reading(item),
    )


def render_engine(case: DecisionCase) -> str:
    engine = build_engine(case)
    lines = ["Scenario engine", "", engine.option, ""]
    for item in engine.cases:
        lines.append(item.name)
        lines.append(item.headline)
        if item.note:
            lines.append(item.note)
        lines.append("")
    lines.append("Variables")
    lines.append("")
    for item in engine.variables:
        lines.append(item.name)
        lines.append(item.detail)
        lines.append("")
    lines.append("What happens if our assumptions change?")
    lines.append("")
    if not engine.chain:
        lines.append(engine.reading)
        return "\n".join(lines).rstrip() + "\n"
    last = len(engine.chain) - 1
    for index, step in enumerate(engine.chain):
        lines.append(step.label)
        lines.append(step.change)
        if step.note:
            lines.append(step.note)
        if index != last:
            lines.append("        ↓")
    if engine.reading:
        lines.extend(["", engine.reading])
    return "\n".join(lines).rstrip() + "\n"


def answer(case: DecisionCase | None, asked: str = "") -> str:
    if case is None:
        return "No stored decision is available to trace.\n"
    body = render_engine(case).rstrip()
    if not asked:
        return body + "\n"
    return f"{asked}\n\n{body}\n"


def _cases(case: DecisionCase, chosen: Option | None) -> list[ScenarioCase]:
    if chosen is None:
        return [ScenarioCase(name, "Not scored yet.") for _key, name in _CASE_NAMES]
    rows: list[ScenarioCase] = []
    for key, name in _CASE_NAMES:
        scenario = case.scenario(chosen.key, key)
        if scenario is None:
            rows.append(ScenarioCase(name, "Not scored yet."))
            continue
        note = ""
        if scenario.blocked_by:
            note = "Blocked. " + " ".join(scenario.blocked_by)
        rows.append(ScenarioCase(name, scenario.headline or "No infrastructure estimate.", note))
    return rows


def _variables(case: DecisionCase, chosen: Option | None, item: WhatIf | None) -> list[ScenarioVariable]:
    capacity = _step(item, "Engineering capacity")
    timeline = _step(item, "Timeline")
    cost = _step(item, "Migration cost")
    return [
        ScenarioVariable("Engineering capacity", _capacity(case, capacity)),
        ScenarioVariable("Timeline", _timeline(case, chosen, timeline)),
        ScenarioVariable("Budget", _budget(cost)),
        ScenarioVariable("Customer adoption", "Not on record."),
        ScenarioVariable("Failure rate", _failure(chosen)),
        ScenarioVariable("Market conditions", "Not on record."),
    ]


def _chain(item: WhatIf) -> list[ChainStep]:
    capacity = _step(item, "Engineering capacity")
    timeline = _step(item, "Timeline")
    cost = _step(item, "Migration cost")
    returned = _step(item, "Expected return")
    confidence = _step(item, "Decision confidence")
    steps = [
        ChainStep("Engineering capacity", f"{capacity.before} → {capacity.after}", capacity.note),
        ChainStep("Timeline", f"{timeline.before} → {timeline.after}", timeline.note),
        ChainStep(f"Cost {_movement(cost.note)}", f"{cost.before} → {cost.after}", cost.note),
        ChainStep(f"ROI {_movement(returned.note)}", f"{returned.before} → {returned.after}", returned.note),
    ]
    change = "changes" if item.changed else "stays"
    note = ""
    if confidence is not None and confidence.before != confidence.after:
        note = f"Confidence moves from {confidence.before} to {confidence.after}."
        if confidence.note:
            note = f"{note} {confidence.note}"
    steps.append(
        ChainStep(
            f"Recommendation {change}",
            f"{item.recommendation_before} → {item.recommendation_after}",
            note,
        )
    )
    return steps


def _reading(item: WhatIf | None) -> str:
    if item is None:
        return "Nothing is scored yet, so a change in assumptions cannot be traced."
    if item.changed:
        return f"The recommendation changes to {item.recommendation_after}."
    return f"The recommendation stays {item.recommendation_after}."


def _capacity(case: DecisionCase, step) -> str:
    limit = _limit(case, "headcount")
    if limit is None:
        return "Not on record."
    noun = "engineer is" if limit == 1 else "engineers are"
    text = f"{plain(limit)} {noun} available."
    needy = [
        option
        for option in case.options
        if option.engineers is not None and option.engineers > limit
    ]
    if needy:
        option = max(needy, key=lambda item: item.engineers or 0)
        text += f" {option.name} needs {plain(option.engineers)}."
    if step is not None and step.before != step.after:
        text += f" This question moves {step.before} to {step.after}."
    return text


def _timeline(case: DecisionCase, chosen: Option | None, step) -> str:
    limit = _limit(case, "timeline")
    if limit is None:
        return "Not on record."
    unit = "week" if limit == 1 else "weeks"
    text = f"The limit is {plain(limit)} {unit}."
    band = _effort(chosen)
    if chosen is not None and band is not None:
        text += (
            f" {chosen.name} is estimated at {_span(band[1])},"
            f" and the worst case is {_span(band[2])}."
        )
    if step is not None and step.before != step.after:
        text += f" This question moves {step.before} to {step.after}."
    return text


def _budget(step) -> str:
    text = "Not on record. No budget limit is stored, and labor is unknown."
    if step is None or step.before in {"", "Unknown"}:
        return text
    if step.before == step.after:
        return text
    return f"{text} The infrastructure bill while the work runs moves from {step.before} to {step.after}."


def _failure(chosen: Option | None) -> str:
    if chosen is None:
        return "Not on record."
    band = None
    for item in chosen.projections:
        if item.metric_id == "incident_rate":
            band = item
            break
    if band is None:
        return "Not on record."
    return (
        f"{chosen.name} is estimated at {_incidents(band.p50)}."
        f" The best case is {_incidents(band.p10)} and the worst case is {_incidents(band.p90)}."
        " This question does not replace that estimate."
    )


def _chosen(case: DecisionCase) -> Option | None:
    if case.brief is None or not case.brief.recommendation_key:
        return None
    return case.option(case.brief.recommendation_key)


def _step(item: WhatIf | None, label: str):
    if item is None:
        return None
    for step in item.steps:
        if step.label == label:
            return step
    return None


def _movement(note: str) -> str:
    for word in ("increases", "decreases", "stays put"):
        if word in note:
            return word
    return "stays put"


def _effort(option: Option | None) -> tuple[float, float, float] | None:
    if option is None:
        return None
    for item in option.projections:
        if item.metric_id == "effort":
            return item.p10, item.p50, item.p90
    return None


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _span(value: float) -> str:
    unit = "week" if value == 1 else "weeks"
    return f"{plain(value)} {unit}"


def _incidents(value: float) -> str:
    noun = "incident" if value == 1 else "incidents"
    return f"{plain(value)} {noun} a quarter"
