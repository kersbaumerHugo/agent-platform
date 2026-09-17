import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

NAMESPACE = "project:m11-live-smoke"
EXPECTED_MARKER = "M11_LIVE_CONTEXT_OK"
OBJECTIVE = "m11 live context marker"
STEP_INPUT = "return marker"

_DSH_RUN_METRIC = re.compile(
    r'agent_platform_runs_total\{[^}]*runtime="dsh"[^}]*status="succeeded"[^}]*\}'
    r"|"
    r'agent_platform_runs_total\{[^}]*status="succeeded"[^}]*runtime="dsh"[^}]*\}'
)
_MODEL_SUCCESS_METRIC = re.compile(
    r'agent_platform_model_requests_total\{[^}]*status="succeeded"[^}]*\}'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the supervised real DSH context-aware /work smoke."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/artifacts/m11-real-dsh-work-smoke.json"),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
    )
    return parser.parse_args()


def git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def provider_decisions(context_trace: dict[str, Any]) -> list[dict[str, Any]]:
    traces = context_trace.get("provider_traces", [])
    return [
        {
            "provider": trace.get("provider"),
            "context": trace.get("context"),
            "decision": trace.get("decision"),
            "reason_code": trace.get("reason_code"),
            "accepted_count": trace.get("accepted_count"),
            "accepted_sources": trace.get("accepted_sources"),
        }
        for trace in traces
    ]


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    work_request = {
        "objective": OBJECTIVE,
        "contexts": [
            {
                "role": "subject",
                "namespace": NAMESPACE,
            }
        ],
        "steps": [
            {
                "step_id": "live-context",
                "agent_id": "m11-live-smoke",
                "input": STEP_INPUT,
            }
        ],
    }

    with httpx.Client(
        base_url=base_url,
        timeout=args.timeout_seconds,
    ) as client:
        health = client.get("/health")
        health.raise_for_status()

        response = client.post(
            "/work",
            json=work_request,
        )
        response.raise_for_status()
        body = response.json()

        metrics_response = client.get("/metrics")
        metrics_response.raise_for_status()
        metrics = metrics_response.text

    if body.get("status") != "succeeded":
        raise SystemExit(
            "M11.9 smoke failed: Work did not succeed.\n"
            + json.dumps(body, indent=2, sort_keys=True)
        )

    step_results = body.get("step_results", [])
    if len(step_results) != 1:
        raise SystemExit(f"M11.9 smoke failed: expected one step result, got {len(step_results)}.")

    step = step_results[0]
    run = step.get("run", {})
    context_trace = step.get("context_trace")

    if run.get("status") != "succeeded":
        raise SystemExit(
            "M11.9 smoke failed: Run did not succeed.\n" + json.dumps(run, indent=2, sort_keys=True)
        )

    if not isinstance(context_trace, dict):
        raise SystemExit("M11.9 smoke failed: ContextPreparationTrace is missing.")

    output = run.get("output") or ""
    marker_present = EXPECTED_MARKER in output
    dsh_metric_seen = _DSH_RUN_METRIC.search(metrics) is not None
    model_metric_seen = _MODEL_SUCCESS_METRIC.search(metrics) is not None

    rendering = context_trace.get("rendering", {})
    context_hash = rendering.get("content_hash")

    decisions = provider_decisions(context_trace)
    selected_namespace_accepted = any(
        decision.get("context", {}).get("namespace") == NAMESPACE
        and decision.get("decision") == "accept"
        and int(decision.get("accepted_count") or 0) > 0
        for decision in decisions
    )

    checks = {
        "work_succeeded": body.get("status") == "succeeded",
        "run_succeeded": run.get("status") == "succeeded",
        "selected_namespace_accepted": selected_namespace_accepted,
        "prepared_context_hash_present": (
            isinstance(context_hash, str) and context_hash.startswith("sha256:")
        ),
        "expected_marker_returned": marker_present,
        "dsh_runtime_metric_seen": dsh_metric_seen,
        "model_gateway_success_metric_seen": model_metric_seen,
    }

    passed = all(checks.values())

    artifact = {
        "suite_id": "m11-real-dsh-work-smoke-v0",
        "captured_at": datetime.now(UTC).isoformat(),
        "git_revision": git_revision(),
        "passed": passed,
        "checks": checks,
        "work_id": body.get("work_id"),
        "work_status": body.get("status"),
        "step_id": step.get("step_id"),
        "run_id": run.get("run_id"),
        "run_status": run.get("status"),
        "context_ref": {
            "role": "subject",
            "namespace": NAMESPACE,
        },
        "prepared_context_hash": context_hash,
        "provider_decisions": decisions,
        "output_contains_expected_marker": marker_present,
        "output_sha256": sha256_text(output),
        "raw_model_output_included": False,
    }

    serialized = json.dumps(
        artifact,
        indent=2,
        sort_keys=True,
    )

    print(serialized)

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        serialized + "\n",
        encoding="utf-8",
    )

    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
