"""Execution plan for the option a person approved."""

from decision.models import DecisionCase, ExecutionStep, Option
from decision.text import plain


def execution_plan(case: DecisionCase, option: Option) -> list[ExecutionStep]:
    name = option.name.lower()
    if "partial" in name:
        return [
            ExecutionStep(
                id="facade",
                name="Put a strangler facade in front of the service.",
                window="Weeks 1–2",
                guardrail="No traffic moves until the facade is a no-op in production.",
            ),
            ExecutionStep(
                id="slice",
                name="Move the first slice behind the facade.",
                window="Weeks 3–5",
                guardrail="Shadow reads must match for 48 hours before the slice owns writes.",
            ),
            ExecutionStep(
                id="cutover",
                name="Cut over and leave the old path in place.",
                window=f"Week {plain(option.weeks or 6)}",
                guardrail="Roll back if the error rate exceeds 0.5%.",
            ),
        ]
    if "full" in name:
        return [
            ExecutionStep(
                id="staff",
                name="Staff the engineers the full migration requires.",
                window="Before the work starts",
                guardrail="Do not start while headcount is still short.",
            ),
            ExecutionStep(
                id="window",
                name="Schedule the production downtime window.",
                window="Before the cutover",
                guardrail="This step overrides the no-downtime constraint. Record the exception.",
            ),
            ExecutionStep(
                id="extract",
                name="Extract the service and cut over.",
                window=f"{plain(option.weeks or 0)} weeks",
                guardrail="Keep the previous architecture runnable until the new path holds for a week.",
            ),
        ]
    if option.role == "status_quo" or "keep" in name or name == "do nothing":
        limit = _timeline(case)
        window = f"Review again in {plain(limit)} weeks" if limit is not None else "Review on the next cycle"
        return [
            ExecutionStep(
                id="hold",
                name="Leave the current architecture in place.",
                window=window,
                guardrail="Re-open the decision if deployment time or infrastructure cost moves the objective.",
            )
        ]
    return [
        ExecutionStep(
            id="carry",
            name=option.summary,
            window=f"{plain(option.weeks)} weeks" if option.weeks is not None else "Unscheduled",
            guardrail="Stop if a constraint breaks.",
        )
    ]


def _timeline(case: DecisionCase) -> float | None:
    for constraint in case.constraints:
        if constraint.kind == "timeline":
            return constraint.limit
    return None
