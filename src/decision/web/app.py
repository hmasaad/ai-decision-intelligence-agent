"""Local decision board."""

from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from decision.agent import DecisionAgent
from decision.confidence import confidence_label
from decision.errors import DecisionError
from decision.graph import ask as ask_graph
from decision.impact import answer as answer_impact
from decision.memory import recall
from decision.models import CHANNELS, Evidence, Stage
from decision.paths import home as workspace_home
from decision.present import dossier, whatif_view
from decision.reevaluate import payments_regulation
from decision.registry import OPEN_STATUSES, render_registry
from decision.text import slug
from decision.whatif import answer

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
templates.env.globals["confidence_label"] = confidence_label


def create_app() -> FastAPI:
    app = FastAPI(title="AI Decision Intelligence")
    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, error: str = "") -> HTMLResponse:
        agent = DecisionAgent()
        decisions = agent.cases()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "decisions": decisions,
                "priors": agent.priors(),
                "error": error,
                "workspace": str(workspace_home()),
                "counts": _counts(decisions),
            },
        )

    @app.post("/demo")
    def demo() -> RedirectResponse:
        case = DecisionAgent().demo()
        return RedirectResponse(f"/decisions/{case.id}", status_code=303)

    @app.post("/register")
    def register(
        question: str = Form(...),
        goal: str = Form(""),
        context: str = Form(""),
        owner: str = Form(""),
        options: str = Form(""),
        constraints: str = Form(""),
        assumptions: str = Form(""),
        organization: str = Form("Workspace"),
    ) -> RedirectResponse:
        try:
            case = DecisionAgent().register(
                question=question,
                goal=goal,
                context=context,
                owner=owner,
                options=_lines(options),
                constraints=_lines(constraints),
                assumptions=_lines(assumptions),
                organization=organization.strip() or "Workspace",
            )
        except (DecisionError, ValueError) as exc:
            return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
        return RedirectResponse(f"/decisions/{case.id}", status_code=303)

    @app.post("/frame")
    def frame(
        request_text: str = Form(...),
        subject: str = Form(""),
        objective: str = Form(""),
        engineers: str = Form(""),
        weeks: str = Form(""),
        downtime: str = Form(""),
        organization: str = Form("Workspace"),
        asked_by: str = Form(""),
    ) -> RedirectResponse:
        try:
            case = DecisionAgent().frame(
                request=request_text,
                subject=subject,
                objective=objective,
                engineers=_optional_float(engineers),
                weeks=_optional_float(weeks),
                downtime_forbidden=downtime == "forbid",
                organization=organization.strip() or "Workspace",
                asked_by=asked_by,
            )
        except (DecisionError, ValueError) as exc:
            return RedirectResponse(f"/?error={quote(str(exc))}", status_code=303)
        return RedirectResponse(f"/decisions/{case.id}", status_code=303)

    @app.get("/decisions/{case_id}", response_class=HTMLResponse)
    def detail(
        request: Request,
        case_id: str,
        error: str = "",
        from_engineers: str = "",
        engineers: str = "",
        from_weeks: str = "",
        weeks: str = "",
        downtime: str = "",
        graph: str = "",
        impact: str = "",
    ) -> HTMLResponse:
        agent = DecisionAgent()
        case = agent.get(case_id)
        if case is None:
            raise HTTPException(status_code=404)
        stored = agent.cases()
        view = dossier(case, stored)
        if any(value.strip() for value in (from_engineers, engineers, from_weeks, weeks, downtime)):
            view["whatif"] = whatif_view(
                answer(
                    case,
                    engineers=_optional_float(engineers),
                    from_engineers=_optional_float(from_engineers),
                    weeks=_optional_float(weeks),
                    from_weeks=_optional_float(from_weeks),
                    downtime_forbidden=_downtime(downtime),
                )
            )
        return templates.TemplateResponse(
            request,
            "case.html",
            {
                "case": case,
                "view": view,
                "priors": agent.priors(case.pattern),
                "channels": CHANNELS,
                "graph_answer": ask_graph(stored, graph, case.id) if graph.strip() else "",
                "impact_answer": answer_impact(stored, impact, case.id) if impact.strip() else "",
                "registry": render_registry(case),
                "statuses": [item.value for item in OPEN_STATUSES],
                "error": error,
            },
        )

    @app.get("/recall", response_class=HTMLResponse)
    def ask(request: Request, q: str = "") -> HTMLResponse:
        answer_text = DecisionAgent().recall(q) if q.strip() else ""
        return templates.TemplateResponse(
            request,
            "recall.html",
            {"question": q, "answer": answer_text},
        )

    @app.post("/decisions/{case_id}/registry")
    def revise(
        case_id: str,
        goal: str = Form(""),
        question: str = Form(""),
        context: str = Form(""),
        owner: str = Form(""),
        options: str = Form(""),
        constraints: str = Form(""),
        assumptions: str = Form(""),
        status: str = Form(""),
        locked: str = Form(""),
    ) -> RedirectResponse:
        try:
            DecisionAgent().update(
                case_id,
                goal=None if locked == "brief" else goal,
                question=None if locked == "brief" else question,
                context=context,
                owner=owner,
                options=None if locked == "brief" else _lines(options),
                constraints=None if locked == "brief" else _lines(constraints),
                assumptions=_lines(assumptions),
                status=status or None,
            )
        except (DecisionError, ValueError) as exc:
            return _redirect(case_id, str(exc))
        return _redirect(case_id)

    @app.post("/decisions/{case_id}/evidence")
    def add_evidence(
        case_id: str,
        example: str = Form(""),
        statement: str = Form(""),
        source: str = Form(""),
        channel: str = Form("documentation"),
        kind: str = Form("update"),
        confidence: str = Form("0.6"),
        challenges: str = Form(""),
        limit: str = Form(""),
        option_key: str = Form(""),
        stance: str = Form(""),
    ) -> RedirectResponse:
        try:
            evidence = payments_regulation() if example == "regulation" else Evidence(
                id=slug(source or statement[:48] or "update"),
                kind=kind.strip() or "update",
                statement=statement.strip(),
                source=source.strip() or "Update",
                channel=channel,
                observed_at=date.today(),
                confidence=float(confidence),
                option_key=option_key or None,
                stance=stance,
                challenges=challenges,
                limit=_optional_float(limit),
            )
            DecisionAgent().add_evidence(case_id, evidence)
        except (DecisionError, ValueError) as exc:
            return _redirect(case_id, str(exc))
        return _redirect(case_id)

    @app.post("/decisions/{case_id}/review")
    def review(
        case_id: str,
        action: str = Form(...),
        note: str = Form(""),
        approver: str = Form(""),
        option_key: str = Form(""),
    ) -> RedirectResponse:
        return _act(
            case_id,
            lambda agent: agent.review(case_id, action, note, by=approver, option_key=option_key),
        )

    @app.post("/decisions/{case_id}/steps/{step_id}")
    def finish_step(case_id: str, step_id: str) -> RedirectResponse:
        return _act(case_id, lambda agent: agent.complete_step(case_id, step_id))

    @app.post("/decisions/{case_id}/outcomes")
    async def outcomes(case_id: str, request: Request) -> RedirectResponse:
        form = await request.form()
        actuals: dict[str, float] = {}
        try:
            for key, value in form.items():
                if key.startswith("actual_"):
                    actuals[key.removeprefix("actual_")] = float(str(value))
        except ValueError:
            return _redirect(case_id, "Enter a number for each success metric.")

        def act(agent: DecisionAgent):
            return agent.record_outcomes(case_id, actuals)

        return _act(case_id, act)

    @app.post("/decisions/{case_id}/learn")
    def learn_case(case_id: str) -> RedirectResponse:
        return _act(case_id, lambda agent: agent.learn(case_id))

    @app.post("/decisions/{case_id}/revision")
    def revision(
        case_id: str,
        note: str = Form(""),
        approver: str = Form(""),
    ) -> RedirectResponse:
        return _act(case_id, lambda agent: agent.accept_revision(case_id, note, by=approver))

    return app


def _act(case_id: str, action) -> RedirectResponse:
    try:
        action(DecisionAgent())
    except DecisionError as exc:
        return _redirect(case_id, str(exc))
    return _redirect(case_id)


def _redirect(case_id: str, error: str = "") -> RedirectResponse:
    if error:
        return RedirectResponse(f"/decisions/{case_id}?error={quote(error)}", status_code=303)
    return RedirectResponse(f"/decisions/{case_id}", status_code=303)


def _counts(cases: list) -> dict[str, int]:
    return {
        "total": len(cases),
        "waiting": sum(case.status == Stage.briefed for case in cases),
        "moving": sum(case.status in {Stage.executing, Stage.tracking} for case in cases),
        "learned": sum(case.status == Stage.learned for case in cases),
    }


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _optional_float(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)


def _downtime(value: str) -> bool | None:
    if value == "allow":
        return False
    if value == "forbid":
        return True
    return None


app = create_app()
