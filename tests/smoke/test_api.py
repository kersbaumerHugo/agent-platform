from fastapi.testclient import TestClient

from agent_platform.api.main import app


def test_vertical_slice() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    run = client.post(
        "/runs",
        json={
            "agent_id": "demo",
            "input": "hello platform",
        },
    )
    assert run.status_code == 200

    run_body = run.json()
    assert run_body["status"] == "succeeded"
    assert run_body["run_id"]
    assert "[fake-runtime]" in run_body["output"]

    work = client.post(
        "/work",
        json={
            "objective": "Write a LinkedIn post about the homelab.",
            "contexts": [
                {
                    "role": "shared",
                    "namespace": "global",
                },
                {
                    "role": "delivery",
                    "namespace": "app:linkedin",
                },
                {
                    "role": "subject",
                    "namespace": "project:homelab",
                },
            ],
            "steps": [
                {
                    "step_id": "draft",
                    "agent_id": "writer",
                    "input": "Draft the post.",
                },
                {
                    "step_id": "review",
                    "agent_id": "reviewer",
                    "input": "Review the post.",
                },
            ],
        },
    )
    assert work.status_code == 200

    work_body = work.json()
    assert work_body["status"] == "succeeded"
    assert work_body["work_id"]
    assert work_body["failed_step_id"] is None
    assert work_body["contexts"] == [
        {
            "role": "shared",
            "namespace": "global",
        },
        {
            "role": "delivery",
            "namespace": "app:linkedin",
        },
        {
            "role": "subject",
            "namespace": "project:homelab",
        },
    ]
    assert [step_result["step_id"] for step_result in work_body["step_results"]] == [
        "draft",
        "review",
    ]
    assert all(
        step_result["run"]["status"] == "succeeded" for step_result in work_body["step_results"]
    )
    assert all(
        "[fake-runtime]" in step_result["run"]["output"]
        for step_result in work_body["step_results"]
    )

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "agent_platform_runs_total" in metrics.text
