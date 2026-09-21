from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

from agent_platform.adapters.git.local import LocalGitChangeSink
from agent_platform.application.supervised_coding import SupervisedCodingService
from agent_platform.application.supervised_coding_publication import (
    SupervisedCodingPublicationService,
)
from agent_platform.domain.coding import CodingTask
from agent_platform.trust.authoritative_verifier import AuthoritativeVerifier
from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.change_set_materializer import (
    DisposableChangeSetMaterializer,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
    TrustedPublisher,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_binding import ChangeSetVerificationService
from agent_platform.trust.verification_profile import AuthoritativeVerificationProfile
from agent_platform.trust.verified_publication import VerifiedChangePublisher

TASK_ID = UUID("12000000-0000-4000-8000-000000000006")
CHANGED_PATH = "src/agent_platform/application/m12_smoke_fixture.py"
CHANGED_CONTENT = 'MESSAGE = "m12.6 verified publication smoke"\n'


class StaticCodingProducer:
    def __init__(
        self,
        change_set: ChangeSet,
    ) -> None:
        self._change_set = change_set

    async def produce(
        self,
        task: CodingTask,
    ) -> ChangeSet:
        if task.expected_base_revision != self._change_set.base_revision:
            raise RuntimeError("Static producer received an unexpected base revision.")

        return self._change_set


class ControlledPassingVerificationExecutor:
    """Return complete PASS evidence for the exact platform-owned profile."""

    async def execute(
        self,
        *,
        workspace: Path,
        profile: AuthoritativeVerificationProfile,
    ) -> VerificationResult:
        if not workspace.is_dir():
            raise RuntimeError("Verification workspace does not exist.")

        return VerificationResult(
            profile_version=profile.version,
            outcome=VerificationOutcome.PASS,
            reason_code="all_checks_passed",
            steps=tuple(
                VerificationStepResult(
                    check=step.check,
                    outcome=VerificationOutcome.PASS,
                    exit_code=0,
                    summary="controlled_verification_step_passed",
                )
                for step in profile.steps
            ),
        )


def _git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError("Git command failed during M12.6 integration smoke.")

    return result.stdout.strip()


def _create_trusted_repo(
    root: Path,
) -> tuple[Path, str]:
    repo = root / "trusted"
    repo.mkdir()

    _git(repo, "init", "-b", "main")

    readme = repo / "README.md"
    readme.write_text(
        "# M12.6 integration smoke\n",
        encoding="utf-8",
    )

    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.name=Agent Platform Smoke",
        "-c",
        "user.email=agent-platform-smoke@example.invalid",
        "commit",
        "-m",
        "chore: create trusted baseline",
    )

    return repo, _git(repo, "rev-parse", "HEAD")


def _clone_publication_repo(
    trusted_repo: Path,
    publication_repo: Path,
) -> None:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "clone",
            "--local",
            "--no-hardlinks",
            "--no-tags",
            str(trusted_repo),
            str(publication_repo),
        ],
        cwd=trusted_repo.parent,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError("Failed to create disposable publication repository.")


async def _run() -> int:
    with tempfile.TemporaryDirectory(prefix="m12-6-smoke-") as temp_dir:
        root = Path(temp_dir)
        trusted_repo, base_revision = _create_trusted_repo(root)
        publication_repo = root / "publication"
        _clone_publication_repo(
            trusted_repo,
            publication_repo,
        )

        change_set = ChangeSet(
            base_revision=base_revision,
            branch_name=f"coding/{TASK_ID}",
            commit_message=f"chore: apply supervised coding task {TASK_ID}",
            changes=(
                FileChange(
                    path=CHANGED_PATH,
                    operation=FileChangeOperation.UPSERT,
                    content=CHANGED_CONTENT,
                ),
            ),
        )
        expected_identity = identify_change_set(change_set)

        task = CodingTask(
            task_id=TASK_ID,
            goal="Prove the same verified ChangeSet reaches trusted publication.",
            expected_base_revision=base_revision,
        )

        preparation = SupervisedCodingService(
            producer=StaticCodingProducer(change_set),
        )
        materializer = DisposableChangeSetMaterializer(
            trusted_repo_root=trusted_repo,
            workspace_parent=root / "verification-workspaces",
        )
        verifier = AuthoritativeVerifier(
            executor=ControlledPassingVerificationExecutor(),
        )
        verification = ChangeSetVerificationService(
            materializer=materializer,
            verifier=verifier,
        )
        trusted_publisher = TrustedPublisher(
            policy=ChangePolicy(),
            sink=LocalGitChangeSink(publication_repo),
        )
        verified_publisher = VerifiedChangePublisher(
            publisher=trusted_publisher,
        )
        service = SupervisedCodingPublicationService(
            preparation=preparation,
            verification=verification,
            publisher=verified_publisher,
        )

        publication = await service.execute(task)

        published_commit = publication.reference.removeprefix("git:")
        actual_head = _git(publication_repo, "rev-parse", "HEAD")
        actual_parent = _git(publication_repo, "rev-parse", "HEAD^")
        actual_branch = _git(
            publication_repo,
            "branch",
            "--show-current",
        )
        actual_message = _git(
            publication_repo,
            "log",
            "-1",
            "--pretty=%B",
        )
        changed_paths = tuple(
            path
            for path in _git(
                publication_repo,
                "diff",
                "--name-only",
                base_revision,
                "HEAD",
                "--",
            ).splitlines()
            if path
        )
        published_content = (publication_repo / CHANGED_PATH).read_text(encoding="utf-8")

        checks = {
            "authoritative_profile_evidence_complete": (
                len((AuthoritativeVerificationProfile()).steps) == 7
            ),
            "publication_identity_matches_verified_identity": (
                publication.identity == expected_identity
            ),
            "published_commit_matches_reference": (actual_head == published_commit),
            "published_commit_parent_matches_trusted_base": (actual_parent == base_revision),
            "published_branch_matches_change_set": (actual_branch == change_set.branch_name),
            "published_commit_message_matches_change_set": (
                actual_message == change_set.commit_message
            ),
            "published_changed_paths_match_change_set": (changed_paths == change_set.changed_paths),
            "published_content_matches_change_set": (published_content == CHANGED_CONTENT),
            "trusted_baseline_remains_unchanged": (
                _git(trusted_repo, "rev-parse", "HEAD") == base_revision
                and not (trusted_repo / CHANGED_PATH).exists()
            ),
        }

        passed = all(checks.values())

        payload = {
            "candidate_accepted": passed,
            "decision": (
                "same_verified_changeset_reached_trusted_publication"
                if passed
                else "integration_invariant_failed"
            ),
            "change_set_identity": expected_identity.reference,
            "checks": checks,
        }

        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
        )

        return 0 if passed else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
