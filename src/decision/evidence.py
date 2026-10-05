"""Evidence, kept apart from opinion.

A claim names its source, when it was seen, how reliable it is, how fresh it
is, and how much confidence it carries. Reliability says whether the claim is
evidence or opinion. A separate link says which option it supports or
contradicts. A measurement of the current service is evidence, and it is not
filed for or against an option until the record says so.
"""

import re
from datetime import date

from decision.models import CHANNELS, DecisionCase, Evidence, Option


def freshness(observed_at: date, as_of: date | None = None) -> str:
    age = ((as_of or date.today()) - observed_at).days
    if age <= 45:
        return "fresh"
    if age <= 180:
        return "aging"
    return "stale"


def confidence_band(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def reliability(item: Evidence) -> str:
    """What kind of claim this is. Opinion is not given the weight of a measurement."""

    if item.kind in {"opinion", "stakeholder"}:
        return "opinion"
    if item.kind == "feedback" or (item.channel == "customer_feedback" and item.value is None):
        return "opinion"
    if item.kind == "estimate":
        return "estimated"
    if item.kind == "experiment":
        return "observed"
    if item.kind == "precedent" or item.channel == "historical_decision":
        return "historical"
    if item.kind == "market" or item.channel == "market_research":
        return "reported"
    if item.kind in {"constraint", "regulation"}:
        return "recorded"
    if item.kind in {"metric", "incident"} or (item.value is not None and item.confidence >= 0.75):
        return "measured"
    return "recorded"


def relations(case: DecisionCase) -> list[tuple[Evidence, Option, str]]:
    """Each filed link from a claim to an option, as supports or contradicts."""

    found: list[tuple[Evidence, Option, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(item: Evidence, option: Option | None, relation: str) -> None:
        if option is None or relation not in {"supports", "contradicts"}:
            return
        key = (item.id, option.key, relation)
        if key in seen:
            return
        seen.add(key)
        found.append((item, option, relation))

    for item in case.evidence:
        if item.option_key:
            add(item, case.option(item.option_key), item.stance or "supports")
        if item.option_key:
            continue
        named = _named_option(case, item)
        if named is not None:
            add(item, named, "supports")
        limit = _headcount(item)
        if limit is not None:
            for option in case.options:
                if option.engineers is not None and option.engineers > limit:
                    add(item, option, "contradicts")
        position = _downtime(item)
        if position == "forbid":
            for option in case.options:
                if option.requires_downtime:
                    add(item, option, "contradicts")
        elif position == "allow":
            for option in case.options:
                if option.requires_downtime:
                    add(item, option, "supports")
                elif option.weeks and option.weeks > 0:
                    add(item, option, "contradicts")
    return found


def stance_text(case: DecisionCase, item: Evidence) -> str:
    links = [(option, relation) for evidence, option, relation in relations(case) if evidence.id == item.id]
    if not links:
        return "Not filed for or against an option."
    parts = [
        f"{'Supports' if relation == 'supports' else 'Contradicts'} {option.key}. {option.name}."
        for option, relation in links
    ]
    return " ".join(parts)


def balance_lines(case: DecisionCase) -> list[str]:
    opinions = [item for item in case.evidence if reliability(item) == "opinion"]
    evidence_count = len(case.evidence) - len(opinions)
    lines = [f"{_claim_count(evidence_count)} are evidence. {_claim_count(len(opinions))} are opinion."]
    if not case.options:
        return lines
    for option in case.options:
        supports, contradicts = _for_option(case, option)
        lines.append(_tally(option, supports, contradicts))
    return lines


def render_claims(case: DecisionCase, as_of: date | None = None) -> str:
    blocks = ["\n".join(balance_lines(case))]
    for item in case.evidence:
        blocks.append(_render_claim(case, item, as_of))
    return "\n\n".join(blocks) + "\n"


def coverage(evidence: list[Evidence]) -> list[dict[str, object]]:
    counts = {channel: 0 for channel in CHANNELS}
    for item in evidence:
        if item.channel in counts:
            counts[item.channel] += 1
    return [
        {"id": channel, "label": label, "count": counts[channel]}
        for channel, label in CHANNELS.items()
    ]


def _for_option(case: DecisionCase, option: Option) -> tuple[list[Evidence], list[Evidence]]:
    supports: list[Evidence] = []
    contradicts: list[Evidence] = []
    for item, linked, relation in relations(case):
        if linked.key != option.key:
            continue
        if relation == "supports":
            supports.append(item)
        else:
            contradicts.append(item)
    return supports, contradicts


def _tally(option: Option, supports: list[Evidence], contradicts: list[Evidence]) -> str:
    if not supports and not contradicts:
        return f"No evidence is filed for or against {option.key}. {option.name}."
    line = (
        f"{_pieces(len(supports))} of evidence {_verb(len(supports), 'supports', 'support')} "
        f"{option.key}. {option.name}, while {len(contradicts)} {_verb(len(contradicts), 'contradicts', 'contradict')} it."
    )
    notes = []
    opinion_support = sum(reliability(item) == "opinion" for item in supports)
    opinion_contra = sum(reliability(item) == "opinion" for item in contradicts)
    if opinion_support:
        notes.append(f"{opinion_support} of the supporting claims {_be(opinion_support)} opinion.")
    if opinion_contra:
        notes.append(f"{opinion_contra} of the contradictions {_be(opinion_contra)} opinion.")
    if notes:
        line = f"{line} {' '.join(notes)}"
    return line


def _render_claim(case: DecisionCase, item: Evidence, as_of: date | None) -> str:
    fields = [
        ("Source", f"{CHANNELS.get(item.channel, item.channel)} · {item.source}"),
        ("Claim", item.statement),
        ("Timestamp", item.observed_at.isoformat()),
        ("Reliability", reliability(item).capitalize()),
        ("Freshness", freshness(item.observed_at, as_of).capitalize()),
        ("Confidence", f"{confidence_band(item.confidence).capitalize()} · {item.confidence:.2f}"),
        ("Supports / contradicts", stance_text(case, item)),
    ]
    lines = [item.statement]
    last = len(fields) - 1
    for index, (name, value) in enumerate(fields):
        branch = "└──" if index == last else "├──"
        pad = "    " if index == last else "│   "
        lines.append(f"{branch} {name}")
        lines.append(f"{pad}{value}")
    return "\n".join(lines)


def _named_option(case: DecisionCase, item: Evidence) -> Option | None:
    if item.kind != "precedent":
        return None
    text = item.statement.lower()
    matches = [option for option in case.options if option.name.lower() in text]
    if len(matches) == 1:
        return matches[0]
    return None


def _headcount(item: Evidence) -> float | None:
    if item.kind != "constraint" and item.challenges != "headcount":
        return None
    if item.challenges == "headcount" and item.limit is not None:
        return item.limit
    match = re.search(r"(\d+(?:\.\d+)?)\s+engineers", item.statement.lower())
    if match:
        return float(match.group(1))
    return None


def _downtime(item: Evidence) -> str | None:
    if item.challenges == "downtime":
        return "forbid" if item.limit == 0 else "allow"
    text = item.statement.lower()
    if any(phrase in text for phrase in ("will not accept", "not accept", "downtime is forbidden")):
        return "forbid"
    if "production window" in text or "downtime is allowed" in text:
        return "allow"
    return None


def _pieces(count: int) -> str:
    noun = "piece" if count == 1 else "pieces"
    return f"{count} {noun}"


def _verb(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _be(count: int) -> str:
    return "is" if count == 1 else "are"


def _claim_count(count: int) -> str:
    noun = "claim" if count == 1 else "claims"
    return f"{count} {noun}"
