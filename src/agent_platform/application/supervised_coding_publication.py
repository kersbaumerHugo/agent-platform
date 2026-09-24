from __future__ import annotations

import re
from typing import Protocol

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer

from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.verification import VerificationResult
from agent_platform.trust.verification_binding import (
    VerificationRejectedError,
    VerifiedChangeSet,
)
from agent_platform.trust.verified_publication import VerifiedPublicationResult

_GITHUB_PULL_REQUEST_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/([1-9][0-9]*)$"
)

MAX_VERIFICATION_REPAIR_ATTEMPTS = 2


class CodingPreparationService(Protocol):
    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask: ...


class CodingVerificationService(Protocol):
    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet: ...


class CodingRepairProducer(Protocol):
    async def repair(
        self,
        *,
        task: CodingTask,
        candidate: ChangeSet,
        verification: VerificationResult,
        attempt: int,
    ) -> ChangeSet: ...


class CodingVerifiedPublisher(Protocol):
    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult: ...


class CodingPublicationIdentityMismatchError(RuntimeError):
    pass


class CodingTaskIdentityMismatchError(RuntimeError):
    pass


class CodingRepairBaseRevisionMismatchError(RuntimeError):
    pass


class CodingRepairMetadataMismatchError(RuntimeError):
    pass


class CodingRepairNoChangeError(RuntimeError):
    pass


class SupervisedCodingPublicationService:
    """Prepare, verify, repair if needed, and publish one coding task fail-closed."""

    def __init__(
        self,
        *,
        preparation: CodingPreparationService,
        verification: CodingVerificationService,
        publisher: CodingVerifiedPublisher,
        repairer: CodingRepairProducer | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._preparation = preparation
        self._verification = verification
        self._publisher = publisher
        self._repairer = repairer
        self._tracer = tracer or trace.get_tracer("agent_platform.coding")

    async def execute(
        self,
        task: CodingTask,
    ) -> CodingResult:
        with self._tracer.start_as_current_span("coding.supervised") as span:
            span.set_attribute(
                "agent_platform.coding.task.id",
                str(task.task_id),
            )
            span.set_attribute(
                "agent_platform.coding.base_revision",
                task.expected_base_revision,
            )

            try:
                prepared = await self._preparation.execute(task)

                span.set_attribute(
                    "agent_platform.coding.execution.id",
                    str(prepared.execution_id),
                )

                if prepared.task_id != task.task_id:
                    raise CodingTaskIdentityMismatchError(
                        "Prepared coding task identity does not match requested task."
                    )

                candidate = prepared.change_set
                repair_attempts = 0

                while True:
                    try:
                        verified = await self._verification.verify(candidate)
                    except VerificationRejectedError as exc:
                        if (
                            self._repairer is None
                            or repair_attempts >= MAX_VERIFICATION_REPAIR_ATTEMPTS
                        ):
                            raise

                        repair_attempts += 1

                        repaired = await self._repairer.repair(
                            task=task,
                            candidate=candidate,
                            verification=exc.result,
                            attempt=repair_attempts,
                        )

                        self._validate_repair(
                            task=task,
                            previous=candidate,
                            repaired=repaired,
                        )

                        candidate = repaired
                        continue

                    break

                span.set_attribute(
                    "agent_platform.coding.repair.attempts",
                    repair_attempts,
                )

                verification_outcome = CodingVerificationOutcome(
                    verified.verification.outcome.value
                )

                span.set_attribute(
                    "agent_platform.coding.change_set.identity",
                    verified.identity.reference,
                )
                span.set_attribute(
                    "agent_platform.coding.verification.profile",
                    verified.verification.profile_version,
                )
                span.set_attribute(
                    "agent_platform.coding.verification.outcome",
                    verification_outcome.value,
                )

                publication = await self._publisher.publish(verified)

                if publication.identity != verified.identity:
                    raise CodingPublicationIdentityMismatchError(
                        "Published ChangeSet identity does not match verified ChangeSet."
                    )

                pull_request_match = _GITHUB_PULL_REQUEST_PATTERN.fullmatch(publication.reference)
                pull_request_number = (
                    int(pull_request_match.group(1)) if pull_request_match is not None else None
                )

                result = CodingResult(
                    task_id=prepared.task_id,
                    execution_id=prepared.execution_id,
                    base_revision=verified.change_set.base_revision,
                    change_set_identity=verified.identity.reference,
                    changed_paths=verified.change_set.changed_paths,
                    verification_profile_version=verified.verification.profile_version,
                    verification_outcome=verification_outcome,
                    publication_outcome=CodingPublicationOutcome.PUBLISHED,
                    publication_reference=publication.reference,
                    pull_request_number=pull_request_number,
                )

                span.set_attribute(
                    "agent_platform.coding.publication.outcome",
                    result.publication_outcome.value,
                )
                span.set_status(Status(StatusCode.OK))

                return result

            except Exception as exc:
                span.set_attribute(
                    "error.type",
                    type(exc).__name__,
                )
                span.record_exception(exc)
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        type(exc).__name__,
                    )
                )
                raise

    @staticmethod
    def _validate_repair(
        *,
        task: CodingTask,
        previous: ChangeSet,
        repaired: ChangeSet,
    ) -> None:
        if (
            repaired.base_revision != previous.base_revision
            or repaired.base_revision != task.expected_base_revision
        ):
            raise CodingRepairBaseRevisionMismatchError(
                "Repaired ChangeSet must preserve the trusted base revision."
            )

        if (
            repaired.branch_name != previous.branch_name
            or repaired.commit_message != previous.commit_message
        ):
            raise CodingRepairMetadataMismatchError(
                "Repaired ChangeSet must preserve platform-owned publication metadata."
            )

        if identify_change_set(repaired) == identify_change_set(previous):
            raise CodingRepairNoChangeError(
                "Repair attempt did not change the candidate ChangeSet."
            )
