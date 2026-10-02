from datetime import date

from decision.demo import billing_case
from decision.evidence import confidence_band, coverage, freshness
from decision.models import CHANNELS


def test_freshness_follows_the_age_of_the_claim():
    assert freshness(date(2026, 9, 4), date(2026, 10, 2)) == "fresh"
    assert freshness(date(2026, 8, 12), date(2026, 10, 2)) == "aging"
    assert freshness(date(2025, 1, 1), date(2026, 10, 2)) == "stale"


def test_every_billing_claim_has_provenance_and_a_known_source():
    evidence = billing_case().evidence
    seen = {item.channel for item in evidence}
    assert seen == set(CHANNELS)
    for item in evidence:
        assert item.statement
        assert item.source
        assert item.observed_at
        assert 0 <= item.confidence <= 1
        assert confidence_band(item.confidence) in {"high", "medium", "low"}
    counts = {row["id"]: row["count"] for row in coverage(evidence)}
    assert all(counts[channel] >= 1 for channel in CHANNELS)
