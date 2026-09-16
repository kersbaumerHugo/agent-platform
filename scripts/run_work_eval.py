import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from agent_platform.adapters.evaluation.work import WorkEvaluator
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.models import RuntimeRequest, RuntimeResult
from agent_platform.domain.observability import ObservationEvent


class WorkEvalDataset(BaseModel):
    suite_id: str = Field(min_length=1)
    cases: list[EvaluationCase]


class DeterministicEvaluationRuntime:
    @property
    def name(self) -> str:
        return "m9-evaluation"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        if request.input == "__FAIL__":
            raise RuntimeError("planned evaluation failure")

        return RuntimeResult(
            output=f"{request.agent_id}:{request.input}",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M9 work orchestration evaluation suite."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/work/m9_v0.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def load_dataset(path: Path) -> WorkEvalDataset:
    return WorkEvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


async def execute_suite(
    dataset: WorkEvalDataset,
) -> list[EvaluationResult]:
    run_agent = RunAgent(
        runtime=DeterministicEvaluationRuntime(),
        observer=NoopObserver(),
    )
    orchestrator = WorkOrchestrator(
        run_agent=run_agent,
    )
    evaluator = WorkEvaluator(orchestrator)
    runner = EvalRunner(evaluator)

    return await runner.run(dataset.cases)


def normalized_results(
    results: list[EvaluationResult],
) -> list[dict[str, object]]:
    return [result.model_dump(mode="json") for result in results]


async def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)

    started = perf_counter()

    first_results = await execute_suite(dataset)
    second_results = await execute_suite(dataset)

    duration_seconds = perf_counter() - started

    deterministic = normalized_results(first_results) == normalized_results(second_results)
    summary = EvalRunner.summarize(first_results)

    report = {
        "suite_id": dataset.suite_id,
        "case_count": len(dataset.cases),
        "summary": summary,
        "deterministic_reproducibility": deterministic,
        "duration_seconds": duration_seconds,
        "results": normalized_results(first_results),
    }

    serialized_report = json.dumps(
        report,
        indent=2,
        sort_keys=True,
    )

    print(serialized_report)

    if args.output is not None:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.output.write_text(
            serialized_report + "\n",
            encoding="utf-8",
        )

    if (
        not deterministic
        or summary[EvaluationOutcome.FAIL.value] > 0
        or summary[EvaluationOutcome.ERROR.value] > 0
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
