import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from agent_platform.adapters.memory.sqlite import SQLiteMemoryStore
from agent_platform.domain.memory import MemoryRecord, MemoryScope

NAMESPACE = "project:m11-live-smoke"
MARKER = "M11_LIVE_CONTEXT_OK"
MEMORY_ID = UUID("91190000-0000-4000-8000-000000000001")
CONTENT = "m11 live context marker return M11_LIVE_CONTEXT_OK"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the isolated memory database for the M11.9 real DSH smoke."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(".runtime/m11-live-smoke/memory.sqlite3"),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove the smoke database and SQLite sidecar files before seeding.",
    )
    return parser.parse_args()


def reset_database(path: Path) -> None:
    for candidate in (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    ):
        candidate.unlink(missing_ok=True)


async def main() -> None:
    args = parse_args()
    database_path = args.database.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset:
        reset_database(database_path)

    store = SQLiteMemoryStore(database_path)
    await store.store(
        MemoryRecord(
            id=MEMORY_ID,
            scope=MemoryScope(namespace=NAMESPACE),
            content=CONTENT,
            created_at=datetime(
                2026,
                9,
                17,
                12,
                0,
                tzinfo=UTC,
            ),
            metadata={
                "kind": "m11-live-smoke",
            },
        )
    )

    print("M11.9 live-smoke memory seeded.")
    print(f"database: {database_path}")
    print(f"namespace: {NAMESPACE}")
    print(f"memory_id: {MEMORY_ID}")
    print(f"expected_marker: {MARKER}")


if __name__ == "__main__":
    asyncio.run(main())
