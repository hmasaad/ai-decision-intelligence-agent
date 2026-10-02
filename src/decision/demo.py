"""Harbor billing migration: the worked decision."""

from datetime import date

from decision.frame import constraint_set, default_metrics
from decision.models import DecisionCase, Evidence, Option, Projection


def billing_case() -> DecisionCase:
    """A framed migration with estimates, still waiting on a person."""

    return DecisionCase(
        id="billing-migration",
        organization="Harbor",
        request="Should we migrate this service to a new architecture?",
        subject="billing",
        asked_by="Platform",
        objective="Reduce operational cost and deployment time.",
        constraints=constraint_set(3, 8, True),
        metrics=default_metrics(),
        options=[
            Option(
                key="A",
                name="Do nothing",
                summary="Keep the current architecture and change nothing.",
                role="status_quo",
                engineers=0,
                weeks=0,
                requires_downtime=False,
                reversible=True,
                projections=[
                    Projection(metric_id="deploy_time", p10=47, p50=47, p90=47),
                    Projection(metric_id="infra_cost", p10=18400, p50=18400, p90=18400),
                    Projection(metric_id="incident_rate", p10=5, p50=6, p90=8),
                    Projection(metric_id="effort", p10=0, p50=0, p90=0),
                ],
            ),
            Option(
                key="B",
                name="Partial migration",
                summary="Hybrid: keep the service and move the invoice pipeline behind a strangler facade.",
                role="hybrid",
                engineers=3,
                weeks=6,
                requires_downtime=False,
                reversible=True,
                residual_risk="Removing the fallback path early would break the no-downtime rule.",
                projections=[
                    Projection(metric_id="deploy_time", p10=9, p50=12, p90=18),
                    Projection(metric_id="infra_cost", p10=10800, p50=12200, p90=15100),
                    Projection(metric_id="incident_rate", p10=1, p50=2, p90=4),
                    Projection(metric_id="effort", p10=6, p50=6, p90=9),
                ],
            ),
            Option(
                key="C",
                name="Full migration",
                summary="Replace the architecture in one cutover.",
                role="replacement",
                engineers=5,
                weeks=14,
                requires_downtime=True,
                reversible=False,
                projections=[
                    Projection(metric_id="deploy_time", p10=6, p50=8, p90=14),
                    Projection(metric_id="infra_cost", p10=8600, p50=9800, p90=14000),
                    Projection(metric_id="incident_rate", p10=0, p50=1, p90=3),
                    Projection(metric_id="effort", p10=14, p50=14, p90=18),
                ],
            ),
            Option(
                key="D",
                name="Managed billing service",
                summary="Buy a managed billing service instead of migrating this one.",
                role="alternative",
                engineers=2,
                weeks=10,
                requires_downtime=False,
                reversible=True,
                projections=[
                    Projection(metric_id="deploy_time", p10=4, p50=6, p90=15),
                    Projection(metric_id="infra_cost", p10=11000, p50=14000, p90=18000),
                    Projection(metric_id="incident_rate", p10=1, p50=2, p90=5),
                    Projection(metric_id="effort", p10=8, p50=10, p90=14),
                ],
            ),
        ],
        evidence=[
            Evidence(
                id="deploy-now",
                kind="metric",
                statement="Median deploy time for billing is 47 minutes over the last 90 days.",
                source="Deploy logs",
                channel="engineering_metrics",
                observed_at=date(2026, 9, 4),
                confidence=0.92,
                metric_id="deploy_time",
                value=47,
            ),
            Evidence(
                id="release-path",
                kind="metric",
                statement="Billing changes sit on the critical path of 38% of production releases.",
                source="Release analytics",
                channel="product_analytics",
                observed_at=date(2026, 9, 20),
                confidence=0.86,
            ),
            Evidence(
                id="cost-now",
                kind="metric",
                statement="Billing infrastructure costs $18,400 per month.",
                source="Finance review",
                channel="financial",
                observed_at=date(2026, 9, 4),
                confidence=0.88,
                metric_id="infra_cost",
                value=18400,
            ),
            Evidence(
                id="invoice-complaints",
                kind="feedback",
                statement="Invoice delays after billing deploys are a recurring support theme.",
                source="Support themes",
                channel="customer_feedback",
                observed_at=date(2026, 9, 11),
                confidence=0.63,
            ),
            Evidence(
                id="incidents-now",
                kind="incident",
                statement="Billing was involved in 6 incidents last quarter, 4 of them during deploys.",
                source="Incident review",
                channel="incident",
                observed_at=date(2026, 9, 4),
                confidence=0.84,
                metric_id="incident_rate",
                value=6,
            ),
            Evidence(
                id="partial-estimate",
                kind="estimate",
                statement=(
                    "Architecture review estimates a partial migration at 6 weeks with 3 engineers, "
                    "deploy time around 12 minutes, and no production downtime."
                ),
                source="Architecture review",
                channel="documentation",
                observed_at=date(2026, 9, 18),
                confidence=0.58,
                option_key="B",
            ),
            Evidence(
                id="full-estimate",
                kind="estimate",
                statement="A full extraction is estimated at 14 weeks with 5 engineers and a cutover window.",
                source="Architecture review",
                channel="documentation",
                observed_at=date(2026, 9, 18),
                confidence=0.52,
                option_key="C",
            ),
            Evidence(
                id="shadow-read",
                kind="experiment",
                statement="A one-week shadow read of the invoice path matched production with no extra errors.",
                source="Invoice shadow read",
                channel="experiment",
                observed_at=date(2026, 9, 25),
                confidence=0.74,
                option_key="B",
            ),
            Evidence(
                id="notifications-precedent",
                kind="precedent",
                statement=(
                    "The notifications service finished a partial migration in 7 weeks. "
                    "Deploy time fell from 30 minutes to 9. Cost fell 22%."
                ),
                source="Platform retrospective",
                channel="historical_decision",
                observed_at=date(2026, 8, 12),
                confidence=0.7,
            ),
            Evidence(
                id="vendor-quotes",
                kind="market",
                statement="Two managed billing vendors quote about $14,000 per month.",
                source="Vendor quotes",
                channel="market_research",
                observed_at=date(2026, 8, 28),
                confidence=0.6,
                option_key="D",
            ),
            Evidence(
                id="staffing",
                kind="constraint",
                statement="Platform has 3 engineers available for this work.",
                source="Staffing plan",
                channel="knowledge_base",
                observed_at=date(2026, 9, 18),
                confidence=0.8,
            ),
            Evidence(
                id="sre",
                kind="stakeholder",
                statement="SRE will not accept planned production downtime for billing.",
                source="SRE",
                channel="knowledge_base",
                observed_at=date(2026, 9, 18),
                confidence=0.76,
            ),
        ],
    )


OBSERVED = {
    "deploy_time": 15,
    "infra_cost": 12800,
    "incident_rate": 2,
    "effort": 7,
}
