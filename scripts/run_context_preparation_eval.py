import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from agent_platform.adapters.evaluation.context_preparation import (
    ContextPreparationEvaluator,
)
from agent_platform.adapters.memory.context_provider import (
    MemoryContextProvider,
)
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.memory import MemoryRecord
from agent_platform.domain.model import (
    ModelRequest,
    ModelResult,
)
from agent_platform.domain.observability import ObservationEvent


class ContextPreparationEvalDataset(BaseModel):
    suite_id: str = Field(min_length=1)
    memories: list[MemoryRecord]
    cases: list[EvaluationCase]


class DeterministicEvaluationModel:
    @property
    def provider(self) -> str:
        return "m10-eval"

    @property
    def model(self) -> str:
        return "deterministic-v0"

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        return ModelResult(
            provider=self.provider,
            model=self.model,
            output=f"accepted:{len(request.messages)}",
            finish_reason="stop",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic M10 context preparation evaluation suite.")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/context_preparation/m10_v0.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def load_dataset(
    path: Path,
) -> ContextPreparationEvalDataset:
    return ContextPreparationEvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


async def execute_suite(
    dataset: ContextPreparationEvalDataset,
    database_path: Path,
) -> list[EvaluationResult]:
    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)
    acceptance = LexicalRetrievalAcceptanceGate()

    for memory in dataset.memories:
        await store.store(memory)

    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=acceptance,
    )
    gateway = ModelGateway(
        model=DeterministicEvaluationModel(),
        observer=NoopObserver(),
    )
    evaluator = ContextPreparationEvaluator(
        provider=provider,
        model_gateway=gateway,
    )
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

    with tempfile.TemporaryDirectory(prefix="agent-platform-m10-context-eval-") as first_temp_dir:
        first_results = await execute_suite(
            dataset,
            Path(first_temp_dir) / "memory.sqlite3",
        )

    with tempfile.TemporaryDirectory(prefix="agent-platform-m10-context-eval-") as second_temp_dir:
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
