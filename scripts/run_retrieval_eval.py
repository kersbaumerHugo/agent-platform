import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from agent_platform.adapters.evaluation.retrieval import RetrievalEvaluator
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.memory import MemoryRecord


class RetrievalEvalDataset(BaseModel):
    suite_id: str = Field(min_length=1)
    memories: list[MemoryRecord]
    cases: list[EvaluationCase]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M8 retrieval evaluation suite."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/retrieval/m8_v0.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def load_dataset(path: Path) -> RetrievalEvalDataset:
    return RetrievalEvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


async def execute_suite(
    dataset: RetrievalEvalDataset,
    database_path: Path,
) -> list[EvaluationResult]:
    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)
    acceptance = LexicalRetrievalAcceptanceGate()

    for memory in dataset.memories:
        await store.store(memory)

    evaluator = RetrievalEvaluator(
        retrieval=retrieval,
        acceptance=acceptance,
    )
    runner = EvalRunner(evaluator)

    return await runner.run(dataset.cases)


def normalized_results(
    results: list[EvaluationResult],
) -> list[dict[str, object]]:
    return [
        result.model_dump(
            mode="json",
        )
        for result in results
    ]


async def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)

    started = perf_counter()

    with tempfile.TemporaryDirectory(prefix="agent-platform-m8-eval-") as first_temp_dir:
        first_results = await execute_suite(
            dataset,
            Path(first_temp_dir) / "memory.sqlite3",
        )

    with tempfile.TemporaryDirectory(prefix="agent-platform-m8-eval-") as second_temp_dir:
        second_results = await execute_suite(
            dataset,
            Path(second_temp_dir) / "memory.sqlite3",
        )

    duration_seconds = perf_counter() - started

    deterministic = normalized_results(first_results) == normalized_results(second_results)

    summary = EvalRunner.summarize(first_results)

    report = {
        "suite_id": dataset.suite_id,
        "case_count": len(dataset.cases),
        "summary": summary,
        "deterministic_reproducibility": deterministic,
        "duration_seconds": duration_seconds,
        "results": [result.model_dump(mode="json") for result in first_results],
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
