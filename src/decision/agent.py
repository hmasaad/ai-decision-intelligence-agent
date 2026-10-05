"""The decision loop, from a request through the lesson it leaves behind."""

from pathlib import Path

from decision import store
from decision.demo import billing_case
from decision.errors import DecisionError
from decision.alternatives import render_alternatives
from decision.assumptions import render_assumptions
from decision.confidence import render_confidence
from decision.scenarios import render_engine
from decision.evidence import render_claims
from decision.frame import frame_request
from decision.graph import ask as ask_graph
from decision.graph import render_graph
from decision.reason import render_map
from decision.loop import apply_review, complete_step, learn, prepare, record_outcomes
from decision.memory import recall as recall_question
from decision.models import DecisionCase, Evidence, Prior
from decision.reevaluate import accept_revision, incorporate
from decision.registry import apply_update, register_case, render_registry
from decision.store import utc_now
from decision.text import slug


class DecisionAgent:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home

    def register(
        self,
        question: str,
        goal: str = "",
        context: str = "",
        owner: str = "",
        options: list[str] | None = None,
        constraints: list[str] | None = None,
        assumptions: list[str] | None = None,
        organization: str = "Workspace",
    ) -> DecisionCase:
        drafted = register_case(
            question=question,
            goal=goal,
            context=context,
            owner=owner,
            options=options,
            constraints=constraints,
            assumptions=assumptions,
            organization=organization,
        )
        drafted = drafted.model_copy(update={"id": self._unique(drafted.id)})
        return self._save(drafted)

    def update(
        self,
        case_id: str,
        *,
        goal: str | None = None,
        question: str | None = None,
        context: str | None = None,
        owner: str | None = None,
        options: list[str] | None = None,
        constraints: list[str] | None = None,
        assumptions: list[str] | None = None,
        status: str | None = None,
    ) -> DecisionCase:
        case = self._require(case_id)
        return self._save(
            apply_update(
                case,
                goal=goal,
                question=question,
                context=context,
                owner=owner,
                options=options,
                constraints=constraints,
                assumptions=assumptions,
                status=status,
            )
        )

    def inspect(self, case_id: str) -> str:
        return render_registry(self._require(case_id))

    def claims(self, case_id: str) -> str:
        return render_claims(self._require(case_id))

    def assumptions(self, case_id: str) -> str:
        return render_assumptions(self._require(case_id))

    def demo(self) -> DecisionCase:
        return self._save(prepare(billing_case()))

    def frame(
        self,
        request: str,
        subject: str = "",
        objective: str = "",
        engineers: float | None = None,
        weeks: float | None = None,
        downtime_forbidden: bool = False,
        organization: str = "Workspace",
        asked_by: str = "",
    ) -> DecisionCase:
        drafted = frame_request(
            request=request,
            subject=subject,
            objective=objective,
            engineers=engineers,
            weeks=weeks,
            downtime_forbidden=downtime_forbidden,
            organization=organization,
            asked_by=asked_by,
            case_id=self._unique(slug(subject or request[:48])),
        )
        return self._save(prepare(drafted))

    def get(self, case_id: str) -> DecisionCase | None:
        with store.open_db(self.home) as connection:
            return store.get_decision(connection, case_id)

    def cases(self) -> list[DecisionCase]:
        with store.open_db(self.home) as connection:
            return store.list_decisions(connection)

    def recall(self, question: str) -> str:
        return recall_question(self.cases(), question)

    def confidence(self, case_id: str) -> str:
        return render_confidence(self._require(case_id))

    def scenarios(self, case_id: str) -> str:
        return render_engine(self._require(case_id))

    def alternatives(self, case_id: str) -> str:
        return render_alternatives(self._require(case_id))

    def graph(self, question: str = "", decision_id: str = "") -> str:
        if not question.strip():
            case = self._require(decision_id)
            return render_map(case) + "\n" + render_graph(case)
        return ask_graph(self.cases(), question, decision_id)

    def priors(self, pattern: str | None = None) -> list[Prior]:
        with store.open_db(self.home) as connection:
            return store.list_priors(connection, pattern)

    def review(
        self,
        case_id: str,
        action: str,
        note: str = "",
        by: str = "",
        option_key: str = "",
    ) -> DecisionCase:
        case = self._require(case_id)
        return self._save(
            apply_review(
                case,
                action,
                note.strip(),
                utc_now(),
                approved_by=by.strip(),
                option_key=option_key.strip(),
            )
        )

    def complete_step(self, case_id: str, step_id: str) -> DecisionCase:
        case = self._require(case_id)
        return self._save(complete_step(case, step_id))

    def record_outcomes(self, case_id: str, actuals: dict[str, float]) -> DecisionCase:
        case = self._require(case_id)
        return self._save(record_outcomes(case, actuals))

    def accept_revision(self, case_id: str, note: str = "", by: str = "") -> DecisionCase:
        case = self._require(case_id)
        return self._save(accept_revision(case, note.strip(), by.strip()))

    def add_evidence(self, case_id: str, evidence: Evidence) -> DecisionCase:
        case = self._require(case_id)
        return self._save(incorporate(case, evidence))

    def learn(self, case_id: str) -> DecisionCase:
        case = self._require(case_id)
        updated, priors = learn(case)
        saved = self._save(updated)
        with store.open_db(self.home) as connection:
            for prior in priors:
                store.save_prior(connection, prior)
        return saved

    def _require(self, case_id: str) -> DecisionCase:
        case = self.get(case_id)
        if case is None:
            raise DecisionError(f"No decision named {case_id}.")
        return case

    def _unique(self, case_id: str) -> str:
        if self.get(case_id) is None:
            return case_id
        number = 2
        while self.get(f"{case_id}-{number}") is not None:
            number += 1
        return f"{case_id}-{number}"

    def _save(self, case: DecisionCase) -> DecisionCase:
        stamped = case.model_copy(
            update={
                "created_at": case.created_at or utc_now(),
                "updated_at": utc_now(),
            }
        )
        with store.open_db(self.home) as connection:
            store.save_decision(connection, stamped)
        return stamped
