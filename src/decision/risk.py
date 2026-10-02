"""Risks on the option a person is being asked to approve.

Each risk carries a probability, an impact, how soon it would be seen, a
mitigation, and the risk that remains after that mitigation.
"""

from decision.models import Band, DecisionCase, Option, Risk, Scenario
from decision.simulate import recommend
from decision.text import plain


def build_risks(case: DecisionCase, scenarios: list[Scenario], bands: list[Band]) -> list[Risk]:
    key = recommend(case, scenarios)
    chosen = case.option(key) if key else None
    risks: list[Risk] = []
    if chosen is not None and chosen.role in {"hybrid", "replacement"}:
        risks.append(_regression(case, chosen, bands))
        delay = _delay(chosen, scenarios)
        if delay is not None:
            risks.append(delay)
    capacity = _capacity(case, scenarios, key)
    if capacity is not None:
        risks.append(capacity)
    return risks


def _regression(case: DecisionCase, option: Option, bands: list[Band]) -> Risk:
    watched = any(item.kind == "experiment" and item.option_key in {None, option.key} for item in case.evidence)
    wide = any(
        band.option_key == option.key and band.metric_id == "incident_rate" and band.spread >= 0.75
        for band in bands
    )
    residual = "low/medium" if option.reversible else "high"
    detail = f"{option.name} changes the production path."
    if watched:
        detail += " A shadow read has already been run."
    if wide:
        detail += " The incident estimate is still wide."
    if option.residual_risk:
        detail += " " + option.residual_risk
    mitigations = [
        "Staged rollout of one slice",
        "Strangler facade, with no traffic until it is a no-op",
        "Roll back if the error rate exceeds 0.5%",
    ]
    if not option.reversible:
        mitigations = [
            "Keep the previous architecture runnable until the new path holds",
            "Do not start while headcount is still short",
        ]
    return Risk(
        option_key=option.key,
        title="Migration causes production regression",
        likelihood="medium",
        impact="high",
        detectability="high" if watched or option.reversible else "medium",
        mitigations=mitigations,
        residual=residual,
        detail=detail,
    )


def _delay(option: Option, scenarios: list[Scenario]) -> Risk | None:
    worst = _scenario(scenarios, option.key, "pessimistic")
    if worst is None or worst.feasible:
        return None
    if "timeline" not in worst.block_codes:
        return None
    detail = " ".join(worst.blocked_by)
    detail = f"In the worst case, {detail[:1].lower()}{detail[1:]}"
    return Risk(
        option_key=option.key,
        title="Migration delay",
        likelihood="medium",
        impact="high",
        detectability="high",
        mitigations=[
            "Stop and re-evaluate if the work passes the timeline limit",
            "Keep the scope to the planned slice",
        ],
        residual="medium",
        detail=detail,
    )


def _capacity(case: DecisionCase, scenarios: list[Scenario], key: str | None) -> Risk | None:
    chosen = _scenario(scenarios, key, "expected") if key else None
    blocked = None
    for option in case.options:
        if option.key == key or option.engineers is None:
            continue
        expected = _scenario(scenarios, option.key, "expected")
        if expected is None or "headcount" not in expected.block_codes:
            continue
        if chosen is not None and expected.score <= chosen.score + 0.01:
            continue
        blocked = option
        break
    if blocked is None or blocked.engineers is None:
        return None
    available = _limit(case, "headcount")
    have = plain(available) if available is not None else "the current team"
    return Risk(
        option_key=blocked.key,
        title="Engineering capacity",
        likelihood="high",
        impact="high",
        detectability="high",
        mitigations=[
            f"Hold the plan to the {have} engineers on record",
            f"Re-open {blocked.name.lower()} only if headcount reaches {plain(blocked.engineers)}",
        ],
        residual="medium",
        detail=f"{blocked.name} needs {plain(blocked.engineers)} engineers and {have} are available.",
    )


def _scenario(scenarios: list[Scenario], key: str | None, name: str) -> Scenario | None:
    if key is None:
        return None
    for item in scenarios:
        if item.option_key == key and item.name == name:
            return item
    return None


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None
