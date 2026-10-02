"""Records for a decision, from the request through the lesson."""

from datetime import date
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Stage(str, Enum):
    requested = "requested"
    framed = "framed"
    briefed = "briefed"
    deferred = "deferred"
    rejected = "rejected"
    executing = "executing"
    tracking = "tracking"
    learned = "learned"


class Constraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    kind: str
    limit: float | None = None


class MetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    unit: str = ""
    direction: str = "lower"
    weight: float = Field(default=1, gt=0)
    binds: str | None = None

    @model_validator(mode="after")
    def known_direction(self) -> Self:
        if self.direction not in {"lower", "higher"}:
            raise ValueError(f"Metric {self.id} direction must be lower or higher")
        return self


class Projection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    p10: float
    p50: float
    p90: float

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError(
                f"Projection {self.metric_id} must run from p10 through p50 to p90"
            )
        return self


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    summary: str
    engineers: float | None = None
    weeks: float | None = None
    requires_downtime: bool | None = None
    reversible: bool = True
    role: str = ""
    projections: list[Projection] = Field(default_factory=list)
    residual_risk: str = ""

    @model_validator(mode="after")
    def known_role(self) -> Self:
        if self.role not in {"", "status_quo", "hybrid", "replacement", "alternative"}:
            raise ValueError(f"Option {self.key} has an unknown role")
        return self


CHANNELS: dict[str, str] = {
    "product_analytics": "Product analytics",
    "engineering_metrics": "Engineering metrics",
    "financial": "Financial data",
    "customer_feedback": "Customer feedback",
    "historical_decision": "Historical decisions",
    "documentation": "Documentation",
    "experiment": "Experiments",
    "incident": "Incident reports",
    "market_research": "Market research",
    "knowledge_base": "Internal knowledge bases",
}


class Evidence(BaseModel):
    """One claim, with the provenance required to trust it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    statement: str
    source: str
    channel: str
    observed_at: date
    confidence: float = Field(ge=0, le=1)
    metric_id: str | None = None
    value: float | None = None
    option_key: str | None = None
    challenges: str = ""
    limit: float | None = None

    @model_validator(mode="after")
    def known_channel(self) -> Self:
        if self.channel not in CHANNELS:
            names = ", ".join(CHANNELS)
            raise ValueError(f"Evidence {self.id} channel must be one of {names}")
        if self.challenges not in {"", "downtime", "timeline", "headcount"}:
            raise ValueError(f"Evidence {self.id} challenges an unknown assumption")
        if self.challenges in {"timeline", "headcount"} and self.limit is None:
            raise ValueError(f"Evidence {self.id} needs a limit for that assumption")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    name: str
    label: str
    values: dict[str, float]
    feasible: bool
    blocked_by: list[str] = Field(default_factory=list)
    block_codes: list[str] = Field(default_factory=list)
    score: float
    headline: str = ""
    detail: str = ""


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    metric_id: str
    low: float
    mid: float
    high: float
    spread: float


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    title: str
    likelihood: str
    impact: str
    detail: str
    detectability: str = ""
    mitigations: list[str] = Field(default_factory=list)
    residual: str = ""


class DecisionBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_key: str | None
    confidence: str
    rationale: list[str]
    change_conditions: list[str]
    uncertainties: list[str]
    text: str


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    window: str
    guardrail: str
    status: str = "pending"


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    actual: float
    predicted: float
    worse_by: float
    variance: str = ""
    cause: str = ""
    learning: str = ""


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bias: str
    reevaluate: bool
    reason: str
    statements: list[str]
    revisions: list[str]
    text: str


class Prior(BaseModel):
    """A revision carried from one decision to the next of the same pattern."""

    model_config = ConfigDict(extra="forbid")

    id: str
    pattern: str
    metric_id: str
    metric_name: str
    factor: float
    statement: str
    source_id: str


class Reevaluation(BaseModel):
    """Why new evidence sent a decision back to a person."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    statement: str
    assumption: str
    risk: str
    outcome: str
    confidence_before: str
    confidence_after: str


class DecisionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization: str = "Workspace"
    request: str
    subject: str = ""
    asked_by: str = ""
    pattern: str = "general"
    decision: str = ""
    objective: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)
    options: list[Option] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    bands: list[Band] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    brief: DecisionBrief | None = None
    status: Stage = Stage.requested
    review_action: str = ""
    review_note: str = ""
    reviewed_at: str = ""
    approved_by: str = ""
    execution: list[ExecutionStep] = Field(default_factory=list)
    outcomes: list[Outcome] = Field(default_factory=list)
    lesson: Lesson | None = None
    reevaluations: list[Reevaluation] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def option(self, key: str) -> Option | None:
        for item in self.options:
            if item.key == key:
                return item
        return None

    def metric(self, metric_id: str) -> MetricSpec | None:
        for item in self.metrics:
            if item.id == metric_id:
                return item
        return None

    def scenario(self, key: str, name: str) -> Scenario | None:
        for item in self.scenarios:
            if item.option_key == key and item.name == name:
                return item
        return None
