import pytest

from decision.agent import DecisionAgent
from decision.errors import DecisionError
from decision.models import DecisionCase
from decision.graph import render_graph
from decision.registry import render_registry

FLUTTER = "Should we migrate our Flutter app to architecture X?"


def test_register_stores_the_question_without_inventing_options(tmp_path):
    agent = DecisionAgent(tmp_path)
    case = agent.register(FLUTTER)
    assert case.id == "should-we-migrate-our-flutter-app-to-architecture-x"
    assert case.status.value == "requested"
    assert case.options == []
    assert case.brief is None

    loaded = agent.get(case.id)
    assert loaded is not None
    text = agent.inspect(case.id)
    assert text.startswith(FLUTTER)
    assert "├── Goal" in text
    assert "├── Question" in text
    assert FLUTTER in text.split("├── Question", 1)[1].split("├──", 1)[0]
    assert "├── Owner" in text
    assert "├── Status" in text
    assert "│   requested" in text
    assert "└── Outcome" in text
    assert "Not recorded." in text
    assert "Do nothing" not in text
    assert "Managed billing service" not in text
    assert "A. Stay on the current architecture" not in render_graph(case)
    recorded = agent.update(case.id, options=["Stay on the current architecture", "Migrate to architecture X"])
    traced = render_graph(recorded)
    assert "A. Stay on the current architecture" in traced
    assert "Recorded. Not scored yet." in traced


def test_update_then_retrieve_the_same_record(tmp_path):
    agent = DecisionAgent(tmp_path)
    created = agent.register(FLUTTER)
    agent.update(
        created.id,
        goal="Keep the Flutter app shippable during the move.",
        context="The app is in production.",
        owner="Mobile",
        options=["Stay on the current architecture", "Migrate to architecture X"],
        constraints=["No rewrite of the payment screens."],
        assumptions=["Architecture X can host the current screens."],
    )
    loaded = agent.get(created.id)
    assert loaded is not None
    assert loaded.owner == "Mobile"
    assert loaded.objective.startswith("Keep the Flutter app")
    assert [item.name for item in loaded.options] == [
        "Stay on the current architecture",
        "Migrate to architecture X",
    ]
    text = agent.inspect(created.id)
    assert "A. Stay on the current architecture" in text
    assert "B. Migrate to architecture X" in text
    assert "No rewrite of the payment screens." in text
    assert "Architecture X can host the current screens." in text
    assert "Not recorded." in text.split("├── Recommendation", 1)[1].split("├──", 1)[0]


def test_a_briefed_decision_keeps_its_recommendation(tmp_path):
    agent = DecisionAgent(tmp_path)
    agent.demo()
    text = agent.inspect("billing-migration")
    assert "B. Partial migration" in text
    assert "medium" in text
    assert "3 engineers available" in text
    with pytest.raises(DecisionError):
        agent.update("billing-migration", options=["Only one option"])
    agent.update("billing-migration", owner="Platform")
    assert agent.get("billing-migration").owner == "Platform"
    loaded = agent.get("billing-migration")
    assert loaded is not None
    assert loaded.brief is not None
    assert loaded.brief.recommendation_key == "B"


def test_an_older_record_still_loads_without_registry_fields():
    payload = {
        "id": "legacy",
        "request": "Should we keep the current vendor?",
        "decision": "Should we keep the current vendor?",
    }
    case = DecisionCase.model_validate(payload)
    assert case.context == ""
    assert case.owner == ""
    assert case.assumptions == []
    assert "Not recorded." in render_registry(case)
