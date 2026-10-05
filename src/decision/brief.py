"""The decision brief a person reads before approving.

The page names the decision, the option, a measured confidence, why that
option, the assumptions it rests on, the largest recorded risk, what would
move the recommendation, and the next action. Every line comes from the
record already built.
"""

from urllib.parse import parse_qs

from decision.assumptions import driving
from decision.execute import execution_plan
from decision.models import Band, DecisionBrief, DecisionCase, Option, Risk, Scenario
from decision.simulate import recommend
from decision.text import plain
from decision.uncertainty import judgments, return_confidence
from decision.whatif import answer, opening


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
    staged = case.model_copy(
        update={
            "scenarios": scenarios,
            "risks": risks,
            "brief": DecisionBrief(
                recommendation_key=chosen.key if chosen else None,
                confidence=confidence,
                rationale=[],
                change_conditions=list(questions),
                uncertainties=list(uncertainties),
                text="pending",
            ),
        }
    )
    decision = case.decision.strip() or "Not stated."
    if chosen is None:
        return _document(
            decision,
            "Not recommended yet.",
            "Not scored yet.",
            ["No option satisfies the constraints, so there is nothing to recommend."],
            ["None recorded."],
            "None recorded.",
            ["Nothing is scored yet, so a change cannot be traced."],
            "No feasible option is ready for review.",
        )
    assumptions = [item.statement for item in driving(staged)] or ["None recorded."]
    mind = _mind(staged) or ["No probed change moves this recommendation."]
    return _document(
        decision,
        f"{chosen.key}. {chosen.name}",
        _confidence_block(case, chosen, confidence, uncertainties),
        _why(staged, chosen),
        assumptions,
        _biggest(risks),
        mind,
        _action(staged, chosen),
    )


def _document(
    decision: str,
    recommendation: str,
    confidence: str,
    why: list[str],
    assumptions: list[str],
    biggest: str,
    mind: list[str],
    action: str,
) -> str:
    return (
        f"DECISION\n{decision}\n\n"
        f"RECOMMENDATION\n{recommendation}\n\n"
        f"CONFIDENCE\n{confidence}\n\n"
        f"WHY\n{_bullets(why)}\n\n"
        f"KEY ASSUMPTIONS\n{_bullets(assumptions)}\n\n"
        f"BIGGEST RISK\n{biggest}\n\n"
        f"WHAT WOULD CHANGE OUR MIND?\n{_bullets(mind)}\n\n"
        f"NEXT ACTION\n{action}\n"
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


def _confidence_block(
    case: DecisionCase,
    chosen: Option,
    confidence: str,
    uncertainties: list[str],
) -> str:
    measured = return_confidence(case, chosen.key)
    if measured is None:
        percent = "Not scored yet."
        line = f"Confidence is {confidence}."
    else:
        percent = f"{round(measured * 100)}%"
        line = f"Confidence is {confidence}, {percent}."
    if uncertainties:
        line = f"{line} {uncertainties[0]}"
    return f"{percent}\n{line}"


def _why(case: DecisionCase, chosen: Option) -> list[str]:
    baseline = next((item for item in case.options if item.role == "status_quo"), None)
    if baseline is None and case.options:
        baseline = case.options[0]
    chosen_scene = case.scenario(chosen.key, "expected")
    base_scene = case.scenario(baseline.key, "expected") if baseline is not None else None
    lines: list[str] = []
    if baseline is not None and baseline.key == chosen.key:
        lines.append("The current service stays in place. Expected cost and incident rate do not move.")
    else:
        cost = _cost_line(base_scene, chosen_scene)
        if cost:
            lines.append(cost)
        incidents = _incident_line(base_scene, chosen_scene)
        if incidents:
            lines.append(incidents)
    fit = _fit_line(case, chosen)
    if fit:
        lines.append(fit)
    return lines or ["No comparison is on record."]


def _cost_line(baseline: Scenario | None, chosen: Scenario | None) -> str:
    if baseline is None or chosen is None:
        return ""
    before = baseline.values.get("infra_cost")
    after = chosen.values.get("infra_cost")
    if before is None or after is None or before <= 0:
        return ""
    percent = round((before - after) / before * 100)
    if percent > 0:
        move = f"{percent}% lower"
    elif percent < 0:
        move = f"{abs(percent)}% higher"
    else:
        move = "unchanged"
    annual = f" The annual change is {chosen.headline}." if chosen.headline else ""
    return (
        f"Expected infrastructure cost is {move}, "
        f"${after:,.0f} a month against ${before:,.0f}.{annual}"
    )


def _incident_line(baseline: Scenario | None, chosen: Scenario | None) -> str:
    if baseline is None or chosen is None:
        return ""
    before = baseline.values.get("incident_rate")
    after = chosen.values.get("incident_rate")
    if before is None or after is None:
        return ""
    if after < before:
        relation = "against"
    elif after > before:
        relation = "above"
    else:
        relation = "the same as"
    return (
        f"Expected incident rate is {plain(after)} a quarter, "
        f"{relation} {plain(before)} on the current service."
    )


def _fit_line(case: DecisionCase, chosen: Option) -> str:
    parts: list[str] = []
    available = _limit(case, "headcount")
    weeks = _limit(case, "timeline")
    if chosen.engineers is not None and available is not None:
        parts.append(f"uses {plain(chosen.engineers)} of the {plain(available)} available engineers")
    elif chosen.engineers is not None:
        parts.append(f"uses {plain(chosen.engineers)} engineers")
    if chosen.weeks is not None and weeks is not None:
        parts.append(f"{plain(chosen.weeks)} weeks against the {plain(weeks)}-week limit")
    elif chosen.weeks is not None:
        parts.append(f"{plain(chosen.weeks)} weeks")
    if not parts and chosen.requires_downtime is None:
        return ""
    sentence = _join(parts)
    if sentence:
        sentence = sentence[:1].upper() + sentence[1:] + "."
    if chosen.requires_downtime is True:
        downtime = "Production downtime is required."
    elif chosen.requires_downtime is False:
        downtime = "Production downtime is not required."
    else:
        downtime = ""
    return " ".join(part for part in (sentence, downtime) if part)


def _biggest(risks: list[Risk]) -> str:
    if not risks:
        return "None recorded."
    rank = {"high": 3, "medium": 2, "low": 1}
    ordered = sorted(
        risks,
        key=lambda risk: (rank.get(risk.impact, 0), rank.get(risk.likelihood, 0)),
        reverse=True,
    )
    top = ordered[0]
    if top.detail:
        return f"{top.title}. {top.detail}"
    return top.title


def _mind(case: DecisionCase) -> list[str]:
    lines: list[str] = []
    link = opening(case)
    if link:
        item = _asked(case, link)
        if item is not None and item.changed:
            lines.append(_flip(item))
    engineers = _limit(case, "headcount")
    weeks = _limit(case, "timeline")
    if engineers is not None and engineers > 1 and weeks is not None:
        shorter = answer(case, engineers=engineers - 1, from_engineers=engineers, from_weeks=weeks)
        if shorter is not None and shorter.changed:
            timeline = next((step.after for step in shorter.steps if step.label == "Timeline"), "")
            derived = f" The timeline derives to {timeline}." if timeline else ""
            lines.append(
                f"Engineering capacity drops from {plain(engineers)} to {plain(engineers - 1)} engineers."
                f"{derived} The recommendation moves to {shorter.recommendation_after}."
            )
    return lines


def _asked(case: DecisionCase, link: str):
    query = parse_qs(link)

    def number(key: str) -> float | None:
        if key not in query:
            return None
        return float(query[key][0])

    downtime = None
    if "downtime" in query:
        downtime = query["downtime"][0] != "allow"
    return answer(
        case,
        engineers=number("engineers"),
        from_engineers=number("from_engineers"),
        weeks=number("weeks"),
        from_weeks=number("from_weeks"),
        downtime_forbidden=downtime,
    )


def _flip(item) -> str:
    prefix = "what happens if "
    body = item.question
    if body.lower().startswith(prefix):
        body = body[len(prefix):]
        body = body[:1].upper() + body[1:]
    if body.endswith("?"):
        body = body[:-1] + "."
    return f"{body} The recommendation moves to {item.recommendation_after}."


def _action(case: DecisionCase, chosen: Option) -> str:
    steps = execution_plan(case, chosen)
    if not steps:
        return "Human approval required."
    first = steps[0]
    window = f" {first.window}." if first.window else ""
    return f"Human approval required. If approved, the first step is: {first.name}{window}"


def _limit(case: DecisionCase, kind: str) -> float | None:
    for item in case.constraints:
        if item.kind == kind:
            return item.limit
    return None


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
