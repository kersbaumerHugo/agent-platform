from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_platform.adapters.workers.dsh_subprocess import (
    DshSubprocessWorkerExecutor,
)
from agent_platform.worker.model_gateway_preflight import (
    ModelGatewayPreflight,
)
from agent_platform.worker.proposal import (
    WorkerProposalResult,
    WorkerProposalRunner,
)
from agent_platform.worker.publication import (
    TrustedPublicationClient,
)
from agent_platform.worker.reconciliation import (
    WorkerWorkspaceReconciler,
)
from agent_platform.worker.session import (
    WorkerDevelopmentSession,
    WorkerDevelopmentTask,
)
from agent_platform.worker.workspace import (
    DisposableWorkerWorkspace,
)


@dataclass(frozen=True)
class SupervisedWorkerProposalRuntime:
    """Operational composition root for self-development proposals."""

    runner: WorkerProposalRunner
    preflight: ModelGatewayPreflight
    reconciled_workspaces: tuple[str, ...]

    async def run(
        self,
        task: WorkerDevelopmentTask,
    ) -> WorkerProposalResult:
        await self.preflight.check()

        return await self.runner.run(task)


def build_supervised_worker_runtime(
    *,
    repository_url: str,
    workspace_parent: Path,
    publisher_socket_path: Path,
    dsh_home: Path,
    provider: str,
    model: str,
    env: Mapping[str, str],
    base_branch: str = "main",
    profile: str = "sdk",
    request_timeout_seconds: float | None = 120.0,
    hard_timeout_seconds: float = 300.0,
    terminate_grace_seconds: float = 5.0,
) -> SupervisedWorkerProposalRuntime:
    reconciled = WorkerWorkspaceReconciler(
        workspace_parent=workspace_parent,
    ).reconcile()

    gateway_base_url = env.get(
        "DEEPSEEK_BASE_URL",
        "",
    ).strip()

    gateway_api_key = env.get(
        "DEEPSEEK_API_KEY",
        "",
    ).strip()

    if not gateway_base_url:
        raise ValueError("Worker runtime environment must include DEEPSEEK_BASE_URL.")

    if not gateway_api_key:
        raise ValueError("Worker runtime environment must include DEEPSEEK_API_KEY.")

    preflight = ModelGatewayPreflight(
        base_url=gateway_base_url,
        api_key=gateway_api_key,
        model=model,
    )

    executor = DshSubprocessWorkerExecutor(
        dsh_home=dsh_home,
        provider=provider,
        model=model,
        profile=profile,
        request_timeout_seconds=request_timeout_seconds,
        hard_timeout_seconds=hard_timeout_seconds,
        terminate_grace_seconds=terminate_grace_seconds,
        env=env,
    )

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=repository_url,
            workspace_parent=workspace_parent,
            base_branch=base_branch,
        ),
        executor=executor,
    )

    runner = WorkerProposalRunner(
        session=session,
        publisher=TrustedPublicationClient(
            socket_path=publisher_socket_path,
        ),
    )

    return SupervisedWorkerProposalRuntime(
        runner=runner,
        preflight=preflight,
        reconciled_workspaces=reconciled,
    )
