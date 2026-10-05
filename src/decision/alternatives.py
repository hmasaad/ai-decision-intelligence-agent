"""Generate more than one way to decide, then grade every option the same way.

The search looks for a first, second, and third option, a status quo, and a
hybrid. Grades come from the expected case already on the record. They say
where each option sits among the others. A blocked option stays in the table.
"""

from decision.models import DecisionCase, Option
from decision.simulate import blocks


def migration_options() -> list[Option]:
    return [
        Option(
            key="A",
            name="Do nothing",
            summary="Keep the current architecture and change nothing.",
            role="status_quo",
        ),
        Option(
            key="B",
            name="Partial migration",
            summary="Hybrid: keep the service and move one slice behind a strangler facade.",
            role="hybrid",
        ),
        Option(
            key="C",
            name="Full migration",
            summary="Replace the architecture in one cutover.",
            role="replacement",
        ),
        Option(
            key="D",
            name="Managed billing service",
            summary="Buy a managed billing service instead of migrating this one.",
            role="alternative",
        ),
    ]


def complete_alternatives(options: list[Option], pattern: str) -> list[Option]:
    """Always keep a status-quo option. A migration also keeps a hybrid."""

    if pattern == "migration" and not options:
        return migration_options()
    labeled = [_label(option) for option in options]
    if not any(option.role == "status_quo" for option in labeled):
        labeled = [_status_quo(_keys(labeled))] + labeled
    if pattern == "migration" and not any(option.role == "hybrid" for option in labeled):
        labeled.append(_hybrid(_keys(labeled)))
    return labeled


def _label(option: Option) -> Option:
    if option.role:
        return option
    name = option.name.lower()
    if name in {"do nothing", "keep current architecture"} or "status quo" in name:
        role = "status_quo"
    elif any(token in name for token in ("partial", "hybrid", "strangler")):
        role = "hybrid"
    elif "full" in name:
        role = "replacement"
    else:
        role = "alternative"
    return option.model_copy(update={"role": role})


def _keys(options: list[Option]) -> set[str]:
    return {option.key for option in options}


def _next_key(used: set[str]) -> str:
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter not in used:
            return letter
    return "Z"


def _status_quo(used: set[str]) -> Option:
    return Option(
        key=_next_key(used),
        name="Do nothing",
        summary="Leave the current state unchanged.",
        role="status_quo",
    )


def _hybrid(used: set[str]) -> Option:
    return Option(
        key=_next_key(used),
        name="Partial migration",
        summary="Hybrid: keep the service and move one slice behind a strangler facade.",
        role="hybrid",
    )


_ROLES = {
    "status_quo": "Status quo",
    "hybrid": "Hybrid",
    "replacement": "Replacement",
    "alternative": "Alternative",
}

_BASIS = (
    "Cost is the expected infrastructure cost. "
    "Time is the expected engineering effort. "
    "Risk is the expected incident rate. "
    "Expected value is the annual infrastructure change against the status quo. "
    "The words place each option among the others on this decision."
)


class CriterionRow:
    def __init__(
        self,
        key: str,
        name: str,
        role: str,
        cost: str,
        time: str,
        risk: str,
        value: str,
        note: str,
        recommended: bool,
        benefit: float | None,
        feasible: bool,
        blocked: list[str],
    ) -> None:
        self.key = key
        self.name = name
        self.role = role
        self.cost = cost
        self.time = time
        self.risk = risk
        self.value = value
        self.note = note
        self.recommended = recommended
        self.benefit = benefit
        self.feasible = feasible
        self.blocked = blocked

    @property
    def label(self) -> str:
        return f"{self.key}. {self.name}"


class Comparison:
    def __init__(self, slots: list[tuple[str, str]], also: str, rows: list[CriterionRow], reading: str) -> None:
        self.slots = slots
        self.also = also
        self.rows = rows
        self.reading = reading
        self.basis = _BASIS


def compare(case: DecisionCase) -> Comparison:
    """Find the spread of alternatives and grade each one on the same criteria."""

    options = case.options
    slots = [
        ("Option A", _slot(options, 0)),
        ("Option B", _slot(options, 1)),
        ("Option C", _slot(options, 2)),
        ("Status quo", _by_role(options, "status_quo")),
        ("Hybrid", _by_role(options, "hybrid")),
    ]
    also = _also(options)
    if not options:
        return Comparison(slots, also, [], "No options are on record, so there is nothing to grade.")
    rows = _rows(case)
    return Comparison(slots, also, rows, _reading(case, rows))


def render_alternatives(case: DecisionCase) -> str:
    found = compare(case)
    lines = ["Alternatives", ""]
    for label, value in found.slots:
        lines.append(f"{label}: {value}")
    if found.also:
        lines.append(f"Also on the table: {found.also}")
    lines.append("")
    if not found.rows:
        lines.append(found.reading)
        return "\n".join(lines) + "\n"
    header = ("Option", "Cost", "Time", "Risk", "Expected value")
    body = [
        (row.label, row.cost, row.time, row.risk, row.value)
        for row in found.rows
    ]
    widths = [max(len(header[index]), *(len(item[index]) for item in body)) for index in range(5)]
    lines.append(_cells(header, widths))
    for row, cells in zip(found.rows, body, strict=True):
        lines.append(_cells(cells, widths))
        if row.note:
            lines.append(f"  {row.note}")
    lines.extend(["", found.basis, "", found.reading])
    return "\n".join(lines) + "\n"


def _rows(case: DecisionCase) -> list[CriterionRow]:
    prepared = [_measure(case, option) for option in case.options]
    scored = [item for item in prepared if item["values"]]
    cost = _scale(scored, "infra_cost")
    time = _scale(scored, "effort")
    risk = _scale(scored, "incident_rate")
    benefits = [item["benefit"] for item in scored if item["benefit"] is not None]
    chosen = case.brief.recommendation_key if case.brief else None
    rows: list[CriterionRow] = []
    for item in prepared:
        option = item["option"]
        if not item["values"]:
            grade = ("Not scored yet.",) * 4
        else:
            values = item["values"]
            assert isinstance(values, dict)
            grade = (
                _word(values.get("infra_cost"), cost),
                _pace(values.get("effort"), time),
                _word(values.get("incident_rate"), risk),
                _word(item["benefit"], (min(benefits), max(benefits)) if benefits else None),
            )
        rows.append(
            CriterionRow(
                key=option.key,
                name=option.name,
                role=_ROLES.get(option.role, ""),
                cost=grade[0],
                time=grade[1],
                risk=grade[2],
                value=grade[3],
                note=_note(item, option.key == chosen),
                recommended=option.key == chosen,
                benefit=item["benefit"],
                feasible=item["feasible"],
                blocked=item["blocked"],
            )
        )
    return rows


def _measure(case: DecisionCase, option: Option) -> dict[str, object]:
    scenario = case.scenario(option.key, "expected")
    if scenario is not None:
        values = dict(scenario.values)
        headline = scenario.headline
        blocked = list(scenario.blocked_by)
        feasible = scenario.feasible
    else:
        values = {item.metric_id: item.p50 for item in option.projections}
        headline = ""
        blocked = []
        feasible = True
        if values and option.engineers is not None and option.weeks is not None and option.requires_downtime is not None:
            blocked, _codes = blocks(case, option, values)
            feasible = not blocked
    benefit = _benefit(case, values)
    if not headline and values:
        headline = _headline(benefit)
    return {
        "option": option,
        "values": values,
        "headline": headline,
        "blocked": blocked,
        "feasible": feasible,
        "benefit": benefit,
    }


def _benefit(case: DecisionCase, values: dict[str, float]) -> float | None:
    if "infra_cost" not in values:
        return None
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if baseline is None and case.options:
        baseline = case.options[0]
    if baseline is None:
        return None
    base = case.scenario(baseline.key, "expected")
    if base is not None and "infra_cost" in base.values:
        base_cost = base.values["infra_cost"]
    else:
        projected = next((item.p50 for item in baseline.projections if item.metric_id == "infra_cost"), None)
        if projected is None:
            return None
        base_cost = projected
    return (base_cost - values["infra_cost"]) * 12


def _headline(benefit: float | None) -> str:
    if benefit is None or abs(benefit) < 1:
        return "No change"
    kind = "benefit" if benefit > 0 else "loss"
    return f"${abs(benefit):,.0f} {kind}"


def _scale(items: list[dict[str, object]], metric_id: str) -> tuple[float, float] | None:
    values: list[float] = []
    for item in items:
        raw = item["values"]
        if isinstance(raw, dict) and metric_id in raw:
            values.append(float(raw[metric_id]))
    if not values:
        return None
    return min(values), max(values)


def _word(value: object, scale: tuple[float, float] | None) -> str:
    if scale is None or not isinstance(value, (int, float)):
        return "Not on record."
    low, high = scale
    if high == low:
        return "Medium"
    position = (float(value) - low) / (high - low)
    if position <= 1 / 3:
        return "Low"
    if position >= 2 / 3:
        return "High"
    return "Medium"


def _pace(value: object, scale: tuple[float, float] | None) -> str:
    label = _word(value, scale)
    return {"Low": "Fast", "Medium": "Medium", "High": "Slow", "Not on record.": "Not on record."}[label]


def _note(item: dict[str, object], recommended: bool) -> str:
    option = item["option"]
    assert isinstance(option, Option)
    parts: list[str] = []
    role = _ROLES.get(option.role, "")
    if role:
        parts.append(role + ".")
    if recommended:
        parts.append("Recommended.")
    headline = str(item["headline"])
    if headline:
        parts.append(headline + ("" if headline.endswith(".") else "."))
    blocked = item["blocked"]
    if isinstance(blocked, list) and blocked:
        parts.append("Blocked. " + " ".join(str(line) for line in blocked))
    if not item["values"]:
        return "Not scored yet."
    return " ".join(parts)


def _reading(case: DecisionCase, rows: list[CriterionRow]) -> str:
    scored = [row for row in rows if row.benefit is not None]
    if not scored:
        return "Nothing is scored yet, so the options are not graded."
    best = max(scored, key=lambda row: row.benefit if row.benefit is not None else 0)
    headline = _headline(best.benefit)
    sentences = [f"{best.label} has the highest expected value, {headline}."]
    if not best.feasible and best.blocked:
        sentences.append("It is blocked. " + " ".join(best.blocked))
    chosen = next((row for row in rows if row.recommended), None)
    if chosen is not None:
        sentences.append(f"The recommendation is {chosen.label}.")
    elif case.brief is None or not case.brief.recommendation_key:
        sentences.append("Nothing is recommended yet.")
    return " ".join(sentences)


def _slot(options: list[Option], index: int) -> str:
    if index >= len(options):
        return "Not on record."
    return f"{options[index].key}. {options[index].name}"


def _by_role(options: list[Option], role: str) -> str:
    for option in options:
        if option.role == role:
            return f"{option.key}. {option.name}"
    return "Not on record."


def _also(options: list[Option]) -> str:
    extra = options[3:]
    if not extra:
        return ""
    return ", ".join(f"{option.key}. {option.name}" for option in extra)


def _cells(cells: tuple[str, ...], widths: list[int]) -> str:
    return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()
