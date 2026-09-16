import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from agent_platform.adapters.evaluation.tool import ToolEvaluator
from agent_platform.adapters.tools.diagnostic import DiagnosticEchoTool
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)


class ToolEvalDataset(BaseModel):
    suite_id: str = Field(min_length=1)
    cases: list[EvaluationCase]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the deterministic M8 tool evaluation suite.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/tool/m8_v0.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def load_dataset(path: Path) -> ToolEvalDataset:
    return ToolEvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


async def execute_suite(
    dataset: ToolEvalDataset,
) -> list[EvaluationResult]:
    evaluator = ToolEvaluator(
        [
            DiagnosticEchoTool(),
        ]
    )
    runner = EvalRunner(evaluator)
    return await runner.run(dataset.cases)


async def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)

    started = perf_counter()

    first_results = await execute_suite(dataset)
    second_results = await execute_suite(dataset)

    duration_seconds = perf_counter() - started

    first_normalized = [result.model_dump(mode="json") for result in first_results]
    second_normalized = [result.model_dump(mode="json") for result in second_results]

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
