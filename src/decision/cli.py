"""Command line for framing a decision and walking the loop."""

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from decision.agent import DecisionAgent
from decision.errors import DecisionError
from decision.text import render_frame
from decision.memory import recall
from decision.models import Evidence
from decision.reevaluate import payments_regulation, render_review
from decision.whatif import answer, posed, render_whatif


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decide",
        description="Frame a decision, test the options, and learn from the outcome.",
    )
    parser.add_argument(
        "--home",
        type=Path,
        help="Workspace directory. Defaults to .decision in the current directory.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Load the Harbor billing migration and write the brief")
    commands.add_parser("list", help="List decisions in the workspace")

    show = commands.add_parser("show", help="Print a framed decision")
    show.add_argument("decision_id")

    brief = commands.add_parser("brief", help="Print the decision brief")
    brief.add_argument("decision_id")

    frame = commands.add_parser("frame", help="Frame a request without estimates")
    frame.add_argument("request")
    frame.add_argument("--subject", default="")
    frame.add_argument("--objective", default="")
    frame.add_argument("--engineers", type=float)
    frame.add_argument("--weeks", type=float)
    frame.add_argument("--no-downtime", action="store_true")
    frame.add_argument("--organization", default="Workspace")
    frame.add_argument("--asked-by", default="")

    review = commands.add_parser("review", help="Record a human decision")
    review.add_argument("decision_id")
    review.add_argument("action", choices=["approved", "rejected", "deferred"])
    review.add_argument("--note", default="")
    review.add_argument("--by", default="", help="Who approved the decision")

    step = commands.add_parser("step", help="Mark an execution step done")
    step.add_argument("decision_id")
    step.add_argument("step_id")

    outcome = commands.add_parser("outcome", help="Record actual metric values")
    outcome.add_argument("decision_id")
    outcome.add_argument("actuals", nargs="+", help="metric=value pairs, such as deploy_time=15")

    learn = commands.add_parser("learn", help="Write the lesson and carry priors forward")
    learn.add_argument("decision_id")

    whatif = commands.add_parser("whatif", help="Ask what happens if an assumption changes")
    whatif.add_argument("decision_id")
    whatif.add_argument("--engineers", type=float)
    whatif.add_argument("--from-engineers", type=float)
    whatif.add_argument("--weeks", type=float)
    whatif.add_argument("--from-weeks", type=float)
    whatif.add_argument("--allow-downtime", action="store_true")

    remembered = commands.add_parser("recall", help="Reconstruct why a stored decision was made")
    remembered.add_argument("question")

    incoming = commands.add_parser("evidence", help="Add evidence and re-check the decision")
    incoming.add_argument("decision_id")
    incoming.add_argument("--statement", default="")
    incoming.add_argument("--source", default="")
    incoming.add_argument("--channel", default="documentation")
    incoming.add_argument("--kind", default="update")
    incoming.add_argument("--confidence", type=float, default=0.6)
    incoming.add_argument("--challenges", default="", choices=["", "downtime", "timeline", "headcount"])
    incoming.add_argument("--limit", type=float)
    incoming.add_argument("--regulation", action="store_true", help="Apply the payments-regulation example")

    serve = commands.add_parser("serve", help="Open the decision board")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args(argv)
    if args.home is not None:
        os.environ["DECISION_HOME"] = str(args.home)
    agent = DecisionAgent(args.home)
    try:
        return _dispatch(agent, args)
    except (DecisionError, ValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(agent: DecisionAgent, args: argparse.Namespace) -> int:
    if args.command == "demo":
        case = agent.demo()
        print(f"Loaded {case.id}. Status: {case.status.value}.")
        print()
        print(case.brief.text if case.brief else render_frame(case), end="")
        return 0
    if args.command == "list":
        cases = agent.cases()
        if not cases:
            print("No decisions yet.")
            return 0
        for case in cases:
            recommendation = ""
            if case.brief and case.brief.recommendation_key:
                option = case.option(case.brief.recommendation_key)
                recommendation = f" — {option.name}" if option else ""
            print(f"{case.id}  {case.status.value}{recommendation}  {case.decision}")
        return 0
    if args.command == "show":
        print(render_frame(_require(agent, args.decision_id)), end="")
        return 0
    if args.command == "brief":
        case = _require(agent, args.decision_id)
        if case.brief is None:
            raise DecisionError(f"{case.id} is framed and has no brief yet.")
        print(case.brief.text, end="")
        return 0
    if args.command == "frame":
        case = agent.frame(
            request=args.request,
            subject=args.subject,
            objective=args.objective,
            engineers=args.engineers,
            weeks=args.weeks,
            downtime_forbidden=args.no_downtime,
            organization=args.organization,
            asked_by=args.asked_by,
        )
        print(f"Framed {case.id}. Status: {case.status.value}.")
        print()
        print(render_frame(case), end="")
        return 0
    if args.command == "review":
        case = agent.review(args.decision_id, args.action, args.note, by=args.by)
        print(f"{case.id} is now {case.status.value}.")
        return 0
    if args.command == "step":
        case = agent.complete_step(args.decision_id, args.step_id)
        done = sum(step.status == "done" for step in case.execution)
        print(f"{args.step_id} is done ({done} of {len(case.execution)}).")
        return 0
    if args.command == "outcome":
        case = agent.record_outcomes(args.decision_id, _actuals(args.actuals))
        print(f"{case.id} is now {case.status.value}.")
        return 0
    if args.command == "learn":
        case = agent.learn(args.decision_id)
        if case.lesson is None:
            raise DecisionError(f"{case.id} has no lesson.")
        print(case.lesson.text)
        return 0
    if args.command == "whatif":
        case = _require(agent, args.decision_id)
        if any(
            value is not None
            for value in (args.engineers, args.from_engineers, args.weeks, args.from_weeks)
        ) or args.allow_downtime:
            item = answer(
                case,
                engineers=args.engineers,
                from_engineers=args.from_engineers,
                weeks=args.weeks,
                from_weeks=args.from_weeks,
                downtime_forbidden=False if args.allow_downtime else None,
            )
        else:
            item = posed(case)
        if item is None:
            raise DecisionError(f"{case.id} has no estimates to vary yet.")
        print(render_whatif(item), end="")
        return 0
    if args.command == "recall":
        print(agent.recall(args.question), end="")
        return 0
    if args.command == "evidence":
        case = _require(agent, args.decision_id)
        before = len(case.reevaluations)
        evidence = payments_regulation() if args.regulation else _evidence(args)
        updated = agent.add_evidence(args.decision_id, evidence)
        if len(updated.reevaluations) == before:
            print("No re-evaluation. The evidence does not change an assumption, a risk, or the expected outcome.")
            return 0
        print(render_review(updated.reevaluations[-1], updated.decision), end="")
        return 0
    if args.command == "serve":
        import uvicorn

        from decision.web.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0
    raise DecisionError(f"Unknown command {args.command}.")


def _require(agent: DecisionAgent, case_id: str):
    case = agent.get(case_id)
    if case is None:
        raise DecisionError(f"No decision named {case_id}.")
    return case


def _evidence(args: argparse.Namespace) -> Evidence:
    from datetime import date

    from decision.text import slug

    if not args.statement.strip():
        raise DecisionError("Evidence needs a statement.")
    source = args.source.strip() or "Update"
    return Evidence(
        id=slug(source),
        kind=args.kind,
        statement=args.statement.strip(),
        source=source,
        channel=args.channel,
        observed_at=date.today(),
        confidence=args.confidence,
        challenges=args.challenges,
        limit=args.limit,
    )


def _actuals(pairs: list[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    for pair in pairs:
        if "=" not in pair:
            raise DecisionError(f"Expected metric=value, got {pair}.")
        key, raw = pair.split("=", 1)
        values[key.strip()] = float(raw)
    return values
