"""Evidence provenance: every claim names where it came from and how fresh it is."""

from datetime import date

from decision.models import CHANNELS, Evidence


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


def coverage(evidence: list[Evidence]) -> list[dict[str, object]]:
    counts = {channel: 0 for channel in CHANNELS}
    for item in evidence:
        if item.channel in counts:
            counts[item.channel] += 1
    return [
        {"id": channel, "label": label, "count": counts[channel]}
        for channel, label in CHANNELS.items()
    ]
