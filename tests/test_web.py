from pathlib import Path

from fastapi.testclient import TestClient

from decision.web.app import create_app


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISION_HOME", str(tmp_path))
    return TestClient(create_app())


def test_frame_form_reproduces_the_example(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    empty = client.get("/")
    assert empty.status_code == 200
    assert "No decisions yet." in empty.text
    assert "Manage the decisions in this workspace." in empty.text
    assert "Waiting for a person" in empty.text

    framed = client.post(
        "/frame",
        data={
            "request_text": "Should we migrate this service to a new architecture?",
            "subject": "X",
            "objective": "Reduce operational cost and deployment time.",
            "engineers": "3",
            "weeks": "8",
            "downtime": "forbid",
            "asked_by": "Platform",
        },
        follow_redirects=True,
    )
    assert framed.status_code == 200
    assert "Should service X migrate?" in framed.text
    assert "Do nothing" in framed.text
    assert "Hybrid" in framed.text
    assert "Product analytics" in framed.text
    assert "Framed, and not ready to recommend." in framed.text
    assert "3 engineers available" in framed.text
    assert "8-week timeline" in framed.text
    assert "No production downtime" in framed.text
    assert "Deployment time" in framed.text
    assert "No evidence collected yet." in framed.text


def test_demo_can_be_approved_tracked_and_learned(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    loaded = client.post("/demo", follow_redirects=True)
    assert loaded.status_code == 200
    board = client.get("/")
    assert "Should the billing service migrate?" in board.text
    assert "briefed" in board.text
    assert "B. Partial migration" in board.text
    assert "58% · medium" in board.text
    assert "Should the billing service migrate?" in loaded.text
    assert "B. Partial migration" in loaded.text
    assert "$74,400 benefit" in loaded.text
    assert "$39,600 benefit" in loaded.text
    assert "Dependency failure" in loaded.text
    assert "Resource shortage" in loaded.text
    assert "Timeline slippage" in loaded.text
    assert "Unexpected cost" in loaded.text
    assert "Engineering metrics · Deploy logs" in loaded.text
    assert "High · 0.92" in loaded.text
    assert "Timestamp" in loaded.text
    assert "Freshness" in loaded.text
    assert "Reliability" in loaded.text
    assert "Supports / contradicts" in loaded.text
    assert "10 claims are evidence. 2 claims are opinion." in loaded.text
    assert "3 pieces of evidence support B. Partial migration, while 0 contradict it." in loaded.text
    assert "Partial migration is estimated at 6 weeks." in loaded.text
    assert "Impact if wrong" in loaded.text
    assert "Architecture review, 58%." in loaded.text
    assert "while 2 contradict it." in loaded.text
    assert "Status quo" in loaded.text
    assert "Needs 5 engineers and 3 are available." in loaded.text
    assert "Requires production downtime." in loaded.text
    assert "Needs 9 weeks and the limit is 8 weeks." in loaded.text
    assert "What happens if engineering capacity changes from 5 to 3?" in loaded.text
    assert "5 engineers → 3 engineers" in loaded.text
    assert "8 weeks → 13 weeks" in loaded.text
    assert "$62,954 benefit → $55,800 benefit" in loaded.text
    assert "58% → 49%" in loaded.text
    assert "Inferred" in loaded.text
    assert "Estimated" in loaded.text
    assert "Known" in loaded.text
    assert "Assumed" in loaded.text
    assert "Unknown" in loaded.text
    assert "$74,400 benefit a year" in loaded.text
    assert "6–9 weeks" in loaded.text
    assert "Human approval required" in loaded.text
    assert "Migration causes production regression" in loaded.text
    assert "Roll back if the error rate exceeds 0.5%" in loaded.text
    assert "Residual risk" in loaded.text
    assert "Can the team allocate 2 additional engineers?" in loaded.text
    assert "Why was it made?" in loaded.text
    assert "What evidence existed?" in loaded.text
    assert "Which alternatives were rejected?" in loaded.text
    assert "Not approved yet" in loaded.text

    regulated = client.post(
        "/decisions/billing-migration/evidence",
        data={"example": "regulation"},
        follow_redirects=True,
    )
    assert "Re-evaluation required" in regulated.text
    assert "no longer valid" in regulated.text
    assert "medium → low" in regulated.text
    assert "Human review required" in regulated.text

    approved = client.post(
        "/decisions/billing-migration/review",
        data={"action": "approved", "note": "Ship the invoice slice"},
        follow_redirects=True,
    )
    assert "Put a strangler facade in front of the service." in approved.text
    assert "Ship the invoice slice" in approved.text

    page = approved
    for step_id in ("facade", "slice", "cutover"):
        page = client.post(
            f"/decisions/billing-migration/steps/{step_id}",
            follow_redirects=True,
        )
    assert "Record outcome" in page.text

    recorded = client.post(
        "/decisions/billing-migration/outcomes",
        data={
            "actual_deploy_time": "15",
            "actual_infra_cost": "12800",
            "actual_incident_rate": "2",
            "actual_effort": "7",
        },
        follow_redirects=True,
    )
    assert "Deployment time came in at 15 minutes." in recorded.text
    assert "The expected case was 12 minutes." in recorded.text
    assert "+25%" in recorded.text
    assert "Root cause" in recorded.text
    assert "Architecture review" in recorded.text

    learned = client.post("/decisions/billing-migration/learn", follow_redirects=True)
    assert "Estimate was optimistic." in learned.text
    assert "25%" in learned.text
    assert "Re-evaluate the estimate" in learned.text

    home = client.get("/")
    assert "25% worse than expected" in home.text

    nxt = client.post(
        "/frame",
        data={
            "request_text": "Should we migrate this service to a new architecture?",
            "subject": "search",
            "objective": "Reduce operational cost and deployment time.",
            "engineers": "3",
            "weeks": "8",
            "downtime": "forbid",
        },
        follow_redirects=True,
    )
    assert "Should the search service migrate?" in nxt.text
    assert "Use 15 minutes as the next expected case, not 12 minutes." in nxt.text

    remembered = client.get(
        "/recall",
        params={"q": "Why did we choose partial migration instead of full migration?"},
    )
    assert remembered.status_code == 200
    assert "WHY IT WAS MADE" in remembered.text
    assert "Approved by" in remembered.text
    assert "variance +25%" in remembered.text

    unknown = client.get(
        "/recall",
        params={"q": "Why did we choose PostgreSQL instead of DynamoDB?"},
    )
    assert "No stored decision chose those options." in unknown.text


def test_register_creates_a_decision_that_can_be_inspected(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/register",
        data={"question": "Should we migrate our Flutter app to architecture X?"},
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert "Should we migrate our Flutter app to architecture X?" in created.text
    assert "Registered. Analysis has not started." in created.text
    assert "├── Goal" in created.text
    assert "Not recorded." in created.text
    assert "Do nothing" not in created.text

    updated = client.post(
        "/decisions/should-we-migrate-our-flutter-app-to-architecture-x/registry",
        data={
            "question": "Should we migrate our Flutter app to architecture X?",
            "goal": "Keep the Flutter app shippable during the move.",
            "context": "The app is in production.",
            "owner": "Mobile",
            "options": "Stay on the current architecture\nMigrate to architecture X",
            "constraints": "No rewrite of the payment screens.",
            "assumptions": "Architecture X can host the current screens.",
            "status": "requested",
        },
        follow_redirects=True,
    )
    assert "Mobile" in updated.text
    assert "A. Stay on the current architecture" in updated.text
    assert "B. Migrate to architecture X" in updated.text

    listed = client.get("/")
    assert "Should we migrate our Flutter app to architecture X?" in listed.text
    assert "Mobile" in listed.text


def test_the_graph_answers_from_the_billing_page(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/demo", follow_redirects=True)
    page = client.get(
        "/decisions/billing-migration",
        params={"graph": "Which assumptions are responsible for this decision?"},
    )
    assert "Decision graph" in page.text
    assert "Same criteria" in page.text
    assert "What happens if our assumptions change?" in page.text
    assert "Confidence is 58%, below 60%." in page.text
    assert "Migration causes production regression" in page.text
    assert "Engineering capacity drops below 3 engineers." in page.text
    assert "clearly the best" not in page.text
    assert "ROI decreases" in page.text
    assert "Customer adoption" in page.text
    assert "B. Partial migration" in page.text
    assert "C. Full migration has the highest expected value, $103,200 benefit." in page.text
    assert "Architecture review, 58%." in page.text
    assert "$74,400 benefit" in page.text
    why = client.get(
        "/decisions/billing-migration",
        params={"graph": "Why did you reach this recommendation?"},
    )
    assert "Constraint → Option" in why.text
    assert "because this path reaches it." in why.text
    assert "No evidence on record supports this assumption." in page.text
    assert "Rests on Staffing plan." in page.text
    assert "Blocks Full migration." in page.text
