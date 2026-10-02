from decision.frame import decision_line, frame_request
from decision.loop import prepare
from decision.models import Stage
from decision.text import render_frame

EXAMPLE = """Decision:
Should service X migrate?

Objective:
Reduce operational cost and deployment time.

Options:
A. Do nothing
B. Partial migration
C. Full migration
D. Managed billing service

Constraints:
- 3 engineers available
- 8-week timeline
- No production downtime

Success metrics:
- Deployment time
- Infrastructure cost
- Incident rate
- Engineering effort
"""


def test_unnamed_migration_uses_service_x():
    assert (
        decision_line("Should we migrate this service to a new architecture?", "X")
        == "Should service X migrate?"
    )
    assert (
        decision_line("Should we migrate this service to a new architecture?", "")
        == "Should service X migrate?"
    )


def test_named_service_is_substituted():
    assert (
        decision_line("Should we migrate this service to a new architecture?", "billing")
        == "Should the billing service migrate?"
    )


def test_frame_matches_the_migration_example():
    case = prepare(
        frame_request(
            request="Should we migrate this service to a new architecture?",
            subject="X",
            objective="Reduce operational cost and deployment time.",
            engineers=3,
            weeks=8,
            downtime_forbidden=True,
        )
    )
    assert render_frame(case) == EXAMPLE
    assert case.status is Stage.framed
    assert case.brief is None


def test_other_questions_stay_questions():
    case = prepare(frame_request("Should we raise the price?", objective="Grow revenue."))
    assert case.decision == "Should we raise the price?"
    assert [option.name for option in case.options] == ["Do nothing"]
    assert case.options[0].role == "status_quo"
    assert case.status is Stage.framed
