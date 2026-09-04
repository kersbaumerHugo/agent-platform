from fastapi.testclient import TestClient

from agent_platform.api.main import app


def test_vertical_slice():
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    run = client.post(
        "/runs",
        json={"agent_id": "demo", "input": "hello platform"},
    )
    assert run.status_code == 200

    body = run.json()
    assert body["status"] == "succeeded"
    assert body["run_id"]
    assert "[fake-runtime]" in body["output"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "agent_platform_runs_total" in metrics.text
