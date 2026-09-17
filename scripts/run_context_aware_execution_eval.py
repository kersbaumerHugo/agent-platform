import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from agent_platform.adapters.evaluation.context_aware_execution import (
    ContextAwareExecutionEvaluator,
)
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)


class ContextAwareExecutionEvalDataset(BaseModel):
    suite_id: str = Field(min_length=1)
    cases: list[EvaluationCase]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic M11 context-aware execution evaluation suite.")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/context_aware_execution/m11_v0.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def load_dataset(
    path: Path,
) -> ContextAwareExecutionEvalDataset:
    return ContextAwareExecutionEvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


async def execute_suite(
    dataset: ContextAwareExecutionEvalDataset,
) -> list[EvaluationResult]:
    runner = EvalRunner(ContextAwareExecutionEvaluator())
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

    first_normalized = normalized_results(first_results)
    second_normalized = normalized_results(second_results)
    deterministic = first_normalized == second_normalized
    summary = EvalRunner.summarize(first_results)

    report = {
        "suite_id": dataset.suite_id,
        "case_count": len(dataset.cases),
        "summary": summary,
        "deterministic_reproducibility": deterministic,
        "duration_seconds": duration_seconds,
        "results": first_normalized,
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
