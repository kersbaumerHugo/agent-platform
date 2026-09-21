from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from agent_platform.adapters.capabilities.coding import (
    SupervisedCodingCapability,
)
from agent_platform.adapters.workers.supervised_coding import (
    WorkerCodingChangeProducer,
)
from agent_platform.adapters.workers.trusted_sandbox import (
    TrustedSandboxWorkerExecutor,
)
from agent_platform.application.supervised_coding import (
    SupervisedCodingService,
)
from agent_platform.application.supervised_coding_publication import (
    SupervisedCodingPublicationService,
)
from agent_platform.trust.authoritative_verifier import (
    AuthoritativeVerifier,
)
from agent_platform.trust.change_set_materializer import (
    DisposableChangeSetMaterializer,
)
from agent_platform.trust.verification_binding import (
    ChangeSetVerificationService,
)
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
    DockerVerificationProcessRunner,
)
from agent_platform.trust.verification_executor import (
    ProfileVerificationExecutor,
)
from agent_platform.trust.verified_publication import (
    VerifiedChangePublisher,
)
from agent_platform.worker.publication import (
    TrustedPublicationAuthorityClient,
    TrustedPublicationClient,
)
from agent_platform.worker.session import (
    WorkerDevelopmentSession,
)
from agent_platform.worker.workspace import (
    DisposableWorkerWorkspace,
)


def build_supervised_coding_capability(
    env: Mapping[str, str],
) -> SupervisedCodingCapability:
    repository_url = _required(
        env,
        "AGENT_PLATFORM_CODING_REPOSITORY_URL",
    )
    trusted_repository = Path(
        _required(
            env,
            "AGENT_PLATFORM_CODING_TRUSTED_REPOSITORY_PATH",
        )
    )
    worker_workspace_parent = _existing_directory(
        env,
        "AGENT_PLATFORM_CODING_WORKSPACE_PARENT",
    )
    sandbox_socket = Path(
        _required(
            env,
            "AGENT_PLATFORM_CODING_SANDBOX_SOCKET",
        )
    )
    verification_workspace_parent = Path(
        _required(
            env,
            "AGENT_PLATFORM_CODING_VERIFICATION_WORKSPACE_PARENT",
        )
    )
    verifier_runtime_root = _existing_directory(
        env,
        "AGENT_PLATFORM_CODING_VERIFIER_RUNTIME_ROOT",
    )
    verifier_image = _required(
        env,
        "AGENT_PLATFORM_CODING_VERIFIER_IMAGE",
    )
    publisher_socket = Path(
        _required(
            env,
            "AGENT_PLATFORM_CODING_PUBLISHER_SOCKET",
        )
    )

    base_branch = env.get(
        "AGENT_PLATFORM_CODING_BASE_BRANCH",
        "main",
    ).strip()

    if not base_branch:
        raise ValueError("AGENT_PLATFORM_CODING_BASE_BRANCH must not be blank.")

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=repository_url,
            workspace_parent=worker_workspace_parent,
            base_branch=base_branch,
        ),
        executor=TrustedSandboxWorkerExecutor(
            socket_path=sandbox_socket,
            workspace_root=worker_workspace_parent,
        ),
    )

    preparation = SupervisedCodingService(
        producer=WorkerCodingChangeProducer(
            session=session,
        ),
    )

    verification = ChangeSetVerificationService(
        materializer=DisposableChangeSetMaterializer(
            trusted_repo_root=trusted_repository,
            workspace_parent=verification_workspace_parent,
        ),
        verifier=AuthoritativeVerifier(
            executor=ProfileVerificationExecutor(
                runner=DockerVerificationProcessRunner(
                    config=DockerVerificationConfig(
                        image=verifier_image,
                        runtime_root=verifier_runtime_root,
                    )
                )
            )
        ),
    )

    publisher = VerifiedChangePublisher(
        publisher=TrustedPublicationAuthorityClient(
            TrustedPublicationClient(
                socket_path=publisher_socket,
            )
        )
    )

    service = SupervisedCodingPublicationService(
        preparation=preparation,
        verification=verification,
        publisher=publisher,
    )

    return SupervisedCodingCapability(service)


def _required(
    env: Mapping[str, str],
    name: str,
) -> str:
    value = env.get(name, "").strip()

    if not value:
        raise ValueError(f"{name} is required when coding is enabled.")

    return value


def _existing_directory(
    env: Mapping[str, str],
    name: str,
) -> Path:
    path = Path(
        _required(
            env,
            name,
        )
    )

    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{name} must reference an existing directory.") from exc

    if not resolved.is_dir():
        raise ValueError(f"{name} must reference an existing directory.")

    return resolved
