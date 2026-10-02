"""SQLite memory for decisions and the priors they leave behind."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from decision.models import DecisionCase, Prior
from decision.paths import home


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def open_db(root: Path | None = None) -> Iterator[sqlite3.Connection]:
    directory = root or home()
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "decision.db")
    connection.row_factory = sqlite3.Row
    try:
        _migrate(connection)
        yield connection
        connection.commit()
    finally:
        connection.close()


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists decisions (
            id text primary key,
            payload text not null,
            status text not null,
            updated_at text not null
        );
        create table if not exists priors (
            id text primary key,
            pattern text not null,
            payload text not null,
            updated_at text not null
        );
        """
    )


def save_decision(connection: sqlite3.Connection, case: DecisionCase) -> None:
    connection.execute(
        """
        insert into decisions (id, payload, status, updated_at) values (?, ?, ?, ?)
        on conflict(id) do update set
            payload = excluded.payload,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (case.id, case.model_dump_json(), case.status.value, case.updated_at),
    )


def get_decision(connection: sqlite3.Connection, case_id: str) -> DecisionCase | None:
    row = connection.execute("select payload from decisions where id = ?", (case_id,)).fetchone()
    if row is None:
        return None
    return DecisionCase.model_validate_json(row["payload"])


def list_decisions(connection: sqlite3.Connection) -> list[DecisionCase]:
    rows = connection.execute("select payload from decisions order by updated_at desc, id")
    return [DecisionCase.model_validate_json(row["payload"]) for row in rows]


def save_prior(connection: sqlite3.Connection, prior: Prior) -> None:
    connection.execute(
        """
        insert into priors (id, pattern, payload, updated_at) values (?, ?, ?, ?)
        on conflict(id) do update set
            pattern = excluded.pattern,
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (prior.id, prior.pattern, prior.model_dump_json(), utc_now()),
    )


def list_priors(connection: sqlite3.Connection, pattern: str | None = None) -> list[Prior]:
    if pattern is None:
        rows = connection.execute("select payload from priors order by id")
    else:
        rows = connection.execute(
            "select payload from priors where pattern = ? order by id",
            (pattern,),
        )
    return [Prior.model_validate_json(row["payload"]) for row in rows]
