"""Turn a vague request into a structured decision."""

import re

from decision.alternatives import complete_alternatives
from decision.models import Constraint, DecisionCase, MetricSpec
from decision.text import plain

MIGRATION_REQUEST = "Should we migrate this service to a new architecture?"


def is_migration(request: str) -> bool:
    text = request.lower()
    return "migrat" in text and "architect" in text


def decision_line(request: str, subject: str) -> str:
    if is_migration(request):
        name = subject.strip()
        if name.lower() in {"", "x", "service x", "this service"}:
            return "Should service X migrate?"
        pretty = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
        pretty = re.sub(r"\s+service$", "", pretty, flags=re.IGNORECASE)
        return f"Should the {pretty} service migrate?"
    text = " ".join(request.strip().split())
    if not text:
        return "Not stated."
    if not text.endswith("?"):
        text += "?"
    return text[0].upper() + text[1:]


def default_metrics() -> list[MetricSpec]:
    """Success metrics for an architecture migration.

    Deployment time and infrastructure cost carry more weight because a
    migration is usually asked in order to move those two.
    """

    return [
        MetricSpec(
            id="deploy_time",
            name="Deployment time",
            unit="minutes",
            direction="lower",
            weight=1.5,
        ),
        MetricSpec(
            id="infra_cost",
            name="Infrastructure cost",
            unit="USD/month",
            direction="lower",
            weight=1.5,
        ),
        MetricSpec(
            id="incident_rate",
            name="Incident rate",
            unit="incidents/quarter",
            direction="lower",
            weight=1,
        ),
        MetricSpec(
            id="effort",
            name="Engineering effort",
            unit="weeks",
            direction="lower",
            weight=1,
            binds="timeline",
        ),
    ]


def constraint_set(
    engineers: float | None,
    weeks: float | None,
    downtime_forbidden: bool,
) -> list[Constraint]:
    items: list[Constraint] = []
    if engineers is not None:
        noun = "engineer" if engineers == 1 else "engineers"
        items.append(
            Constraint(
                id="headcount",
                statement=f"{plain(engineers)} {noun} available",
                kind="headcount",
                limit=engineers,
            )
        )
    if weeks is not None:
        items.append(
            Constraint(
                id="timeline",
                statement=f"{plain(weeks)}-week timeline",
                kind="timeline",
                limit=weeks,
            )
        )
    if downtime_forbidden:
        items.append(
            Constraint(
                id="downtime",
                statement="No production downtime",
                kind="downtime",
                limit=0,
            )
        )
    return items


def frame_request(
    request: str,
    subject: str = "",
    objective: str = "",
    engineers: float | None = None,
    weeks: float | None = None,
    downtime_forbidden: bool = False,
    organization: str = "Workspace",
    asked_by: str = "",
    case_id: str = "",
) -> DecisionCase:
    pattern = "migration" if is_migration(request) else "general"
    return DecisionCase(
        id=case_id or "draft",
        organization=organization,
        request=request.strip(),
        subject=subject.strip(),
        asked_by=asked_by,
        pattern=pattern,
        objective=objective.strip(),
        constraints=constraint_set(engineers, weeks, downtime_forbidden),
        metrics=default_metrics() if pattern == "migration" else [],
        options=complete_alternatives([], pattern),
    )
