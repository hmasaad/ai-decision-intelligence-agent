"""The decision brief a person reads before approving."""

from decision.models import Band, DecisionBrief, DecisionCase, Option, Risk, Scenario
from decision.simulate import recommend
from decision.text import plain
from decision.uncertainty import judgments, return_confidence


def write_brief(
    case: DecisionCase,
    scenarios: list[Scenario],
    bands: list[Band],
    risks: list[Risk],
) -> DecisionBrief:
    key = recommend(case, scenarios)
    chosen = case.option(key) if key else None
    confidence = _confidence(case, key, bands)
    questions = _questions(case, scenarios, key)
    rationale = _rationale(case, scenarios, key)
    uncertainties = _uncertainties(case, key)
    text = _text(case, scenarios, chosen, confidence, risks, questions, uncertainties)
    return DecisionBrief(
        recommendation_key=key,
        confidence=confidence,
        rationale=rationale,
        change_conditions=questions,
        uncertainties=uncertainties,
        text=text,
    )


def _confidence(case: DecisionCase, key: str | None, bands: list[Band]) -> str:
    if key is None or len(case.evidence) < 3:
        return "low"
    spreads = [band.spread for band in bands if band.option_key == key]
    mean = sum(spreads) / len(spreads) if spreads else 1
    precedent = any(item.kind == "precedent" for item in case.evidence)
    if len(case.evidence) >= 6 and precedent and mean <= 0.4:
        return "high"
    return "medium"


def _expected(scenarios: list[Scenario], key: str) -> Scenario | None:
    for item in scenarios:
        if item.option_key == key and item.name == "expected":
            return item
    return None


def _rationale(case: DecisionCase, scenarios: list[Scenario], key: str | None) -> list[str]:
    lines: list[str] = []
    if key is None:
        lines.append("No option satisfies the constraints, so there is nothing to recommend.")
        return lines
    chosen = case.option(key)
    assert chosen is not None
    lines.append(f"{chosen.key}. {chosen.name} is the best option that satisfies the constraints.")
    chosen_score = _expected(scenarios, key)
    for option in case.options:
        if option.key == key:
            continue
        expected = _expected(scenarios, option.key)
        if expected is None or chosen_score is None:
            continue
        if not expected.feasible and expected.score > chosen_score.score + 0.01:
            blocked = " ".join(expected.blocked_by)
            lines.append(
                f"{option.key}. {option.name} scores higher on the weighted metrics and is blocked. {blocked}"
            )
        elif not expected.feasible:
            lines.append(
                f"{option.key}. {option.name} is blocked. {' '.join(expected.blocked_by)}"
            )
        elif expected.score + 0.01 < chosen_score.score:
            lines.append(
                f"{option.key}. {option.name} fits the constraints and scores lower."
            )
    worst = next(
        (item for item in scenarios if item.option_key == key and item.name == "pessimistic"),
        None,
    )
    if worst and not worst.feasible:
        lines.append(
            f"In the worst case, {chosen.name.lower()} is no longer inside the constraints. "
            + " ".join(worst.blocked_by)
        )
    heavy = [metric.name for metric in case.metrics if metric.weight > 1]
    if heavy:
        labels = [heavy[0]] + [name[:1].lower() + name[1:] for name in heavy[1:]]
        verb = "carries" if len(heavy) == 1 else "carry"
        lines.append(f"{_join(labels)} {verb} more weight than the other success metrics.")
    return lines


def _questions(case: DecisionCase, scenarios: list[Scenario], key: str | None) -> list[str]:
    questions: list[str] = []
    chosen_score = _expected(scenarios, key) if key else None
    available = next((item.limit for item in case.constraints if item.kind == "headcount"), None)
    for option in case.options:
        if option.key == key:
            continue
        expected = _expected(scenarios, option.key)
        if expected is None or expected.feasible:
            continue
        if chosen_score is not None and expected.score <= chosen_score.score + 0.01:
            continue
        if (
            "headcount" in expected.block_codes
            and option.engineers is not None
            and available is not None
            and option.engineers > available
        ):
            extra = option.engineers - available
            noun = "engineer" if extra == 1 else "engineers"
            questions.append(f"Can the team allocate {plain(extra)} additional {noun}?")
        if "downtime" in expected.block_codes:
            questions.append("Is the downtime requirement negotiable?")
        break
    if key:
        worst = next(
            (item for item in scenarios if item.option_key == key and item.name == "pessimistic"),
            None,
        )
        if worst and "timeline" in worst.block_codes:
            effort = worst.values.get("effort")
            if effort is not None:
                questions.append(f"Can the timeline extend to {plain(effort)} weeks?")
    return questions


def _uncertainties(case: DecisionCase, key: str | None) -> list[str]:
    if key is None:
        return []
    ret = next((item for item in judgments(case, key) if item.id == "return"), None)
    if ret is None or ret.confidence is None:
        return []
    return [f"Expected return is {ret.display}, {ret.stance}, with {ret.percent} confidence."]


def _text(
    case: DecisionCase,
    scenarios: list[Scenario],
    chosen: Option | None,
    confidence: str,
    risks: list[Risk],
    questions: list[str],
    uncertainties: list[str],
) -> str:
    options = "\n".join(f"{item.key}. {item.name}" for item in case.options) or "Not stated."
    evidence = "\n".join(f"• {line}" for line in _evidence(case)) or "• No measured evidence yet."
    scenes = _scenes(scenarios, chosen.key if chosen else None)
    risk_lines = "\n".join(
        f"• {risk.title} — {risk.likelihood} probability, {risk.impact} impact, residual {risk.residual}"
        for risk in risks
    ) or "• None recorded."
    question_lines = "\n".join(f"• {line}" for line in questions) or "• None."
    if chosen is None:
        review = "No feasible option is ready for review."
    else:
        measured = return_confidence(case, chosen.key)
        percent = f", {round(measured * 100)}%" if measured is not None else ""
        review = (
            f"For review: {chosen.key}. {chosen.name}. "
            f"Confidence is {confidence}{percent}. A person makes the call."
        )
    uncertainty = f"\n{uncertainties[0]}" if uncertainties else ""
    return (
        f"DECISION\n{case.decision or 'Not stated.'}\n\n"
        f"OBJECTIVE\n{case.objective.strip() or 'Not stated.'}\n\n"
        f"OPTIONS\n{options}\n\n"
        f"KEY EVIDENCE\n{evidence}\n\n"
        f"SCENARIOS\n{scenes}{uncertainty}\n\n"
        f"KEY RISKS\n{risk_lines}\n\n"
        f"OPEN QUESTIONS\n{question_lines}\n\n"
        f"DECISION STATUS\nHuman approval required\n{review}\n"
    )


def _evidence(case: DecisionCase) -> list[str]:
    ranked = [
        item
        for item in case.evidence
        if item.value is not None and item.option_key is None and item.confidence >= 0.75
    ]
    order = {"infra_cost": 0, "deploy_time": 1, "incident_rate": 2}
    ranked.sort(key=lambda item: (order.get(item.metric_id or "", 9), -item.confidence))
    return [item.statement for item in ranked[:3]]


def _scenes(scenarios: list[Scenario], key: str | None) -> str:
    if key is None:
        return "Not estimated."
    rows: list[tuple[str, str]] = []
    for label, name in (("Best", "optimistic"), ("Expected", "expected"), ("Worst", "pessimistic")):
        scenario = next((item for item in scenarios if item.option_key == key and item.name == name), None)
        rows.append((f"{label}:", scenario.headline if scenario else "Not estimated."))
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label:<{width}}  {value}" for label, value in rows)


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
