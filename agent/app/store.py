"""SQLite persistence layer.

A single-file SQLite database is enough for the MVP: profiles and search results
are stored so the user does not have to re-upload their CV and re-run the search
after a page refresh. Multi-user production would need Postgres instead (see
README).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone

from .config import get_settings
from .schemas import (
    ApplicationKit,
    ApplicationKitResponse,
    CandidateProfile,
    JobMatch,
    JobPosting,
    ProfileResponse,
    SearchCriteria,
    SearchPlan,
    SearchResponse,
    SearchStats,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id           TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    profile_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS searches (
    id            TEXT PRIMARY KEY,
    profile_id    TEXT NOT NULL REFERENCES profiles(id),
    created_at    TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    plan_json     TEXT NOT NULL,
    stats_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    search_id    TEXT NOT NULL REFERENCES searches(id),
    job_id       TEXT NOT NULL,
    score        INTEGER NOT NULL,
    match_json   TEXT NOT NULL,
    PRIMARY KEY (search_id, job_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id          TEXT PRIMARY KEY,
    profile_id  TEXT NOT NULL REFERENCES profiles(id),
    job_id      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    job_json    TEXT NOT NULL,
    kit_json    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_profile ON applications(profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_searches_profile ON searches(profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_matches_search ON matches(search_id, score DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_file, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_sync() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


async def init_db() -> None:
    await asyncio.to_thread(_init_sync)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- Profiles --------------------------------------------------------------
def _save_profile_sync(profile_id: str, filename: str, profile: CandidateProfile) -> str:
    created = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profiles (id, filename, created_at, profile_json) VALUES (?,?,?,?)",
            (profile_id, filename, created, profile.model_dump_json()),
        )
    return created


async def save_profile(profile_id: str, filename: str, profile: CandidateProfile) -> ProfileResponse:
    created = await asyncio.to_thread(_save_profile_sync, profile_id, filename, profile)
    return ProfileResponse(
        profile_id=profile_id,
        profile=profile,
        source_filename=filename,
        created_at=datetime.fromisoformat(created),
    )


def _get_profile_sync(profile_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()


async def get_profile(profile_id: str) -> ProfileResponse | None:
    row = await asyncio.to_thread(_get_profile_sync, profile_id)
    if row is None:
        return None
    return ProfileResponse(
        profile_id=row["id"],
        profile=CandidateProfile.model_validate_json(row["profile_json"]),
        source_filename=row["filename"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


# -- Searches --------------------------------------------------------------
def _save_search_sync(
    search_id: str,
    profile_id: str,
    criteria: SearchCriteria,
    plan: SearchPlan,
    stats: SearchStats,
    matches: list[JobMatch],
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO searches "
            "(id, profile_id, created_at, criteria_json, plan_json, stats_json) VALUES (?,?,?,?,?,?)",
            (
                search_id,
                profile_id,
                _now(),
                criteria.model_dump_json(),
                plan.model_dump_json(),
                stats.model_dump_json(),
            ),
        )
        conn.execute("DELETE FROM matches WHERE search_id = ?", (search_id,))
        conn.executemany(
            "INSERT INTO matches (search_id, job_id, score, match_json) VALUES (?,?,?,?)",
            [(search_id, m.job.id, m.score, m.model_dump_json()) for m in matches],
        )


async def save_search(
    search_id: str,
    profile_id: str,
    criteria: SearchCriteria,
    plan: SearchPlan,
    stats: SearchStats,
    matches: list[JobMatch],
) -> None:
    await asyncio.to_thread(
        _save_search_sync, search_id, profile_id, criteria, plan, stats, matches
    )


def _get_search_sync(search_id: str) -> tuple[sqlite3.Row | None, list[str]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
        if row is None:
            return None, []
        rows = conn.execute(
            "SELECT match_json FROM matches WHERE search_id = ? ORDER BY score DESC", (search_id,)
        ).fetchall()
    return row, [r["match_json"] for r in rows]


async def get_search(search_id: str) -> SearchResponse | None:
    row, match_rows = await asyncio.to_thread(_get_search_sync, search_id)
    if row is None:
        return None
    return SearchResponse(
        search_id=row["id"],
        plan=SearchPlan.model_validate_json(row["plan_json"]),
        stats=SearchStats.model_validate_json(row["stats_json"]),
        matches=[JobMatch.model_validate_json(m) for m in match_rows],
    )


def _list_searches_sync(profile_id: str, limit: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT s.id, s.created_at, s.stats_json, COUNT(m.job_id) AS match_count "
            "FROM searches s LEFT JOIN matches m ON m.search_id = s.id "
            "WHERE s.profile_id = ? GROUP BY s.id ORDER BY s.created_at DESC LIMIT ?",
            (profile_id, limit),
        ).fetchall()


async def list_searches(profile_id: str, limit: int = 20) -> list[dict]:
    rows = await asyncio.to_thread(_list_searches_sync, profile_id, limit)
    return [
        {
            "search_id": r["id"],
            "created_at": r["created_at"],
            "match_count": r["match_count"],
            "stats": json.loads(r["stats_json"]),
        }
        for r in rows
    ]


# -- Application kits ------------------------------------------------------
def _find_job_sync(job_id: str) -> str | None:
    """Find the posting in stored search results.

    The client never has to send the posting body back; the source data stays on
    the server and no kit can be generated for a fabricated posting.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT match_json FROM matches WHERE job_id = ? ORDER BY rowid DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    return row["match_json"] if row else None


async def find_job(job_id: str) -> JobPosting | None:
    raw = await asyncio.to_thread(_find_job_sync, job_id)
    if raw is None:
        return None
    return JobMatch.model_validate_json(raw).job


def _save_application_sync(
    application_id: str, profile_id: str, job: JobPosting, kit: ApplicationKit
) -> str:
    created = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO applications "
            "(id, profile_id, job_id, created_at, job_json, kit_json) VALUES (?,?,?,?,?,?)",
            (application_id, profile_id, job.id, created, job.model_dump_json(), kit.model_dump_json()),
        )
    return created


async def save_application(
    application_id: str, profile_id: str, job: JobPosting, kit: ApplicationKit
) -> ApplicationKitResponse:
    created = await asyncio.to_thread(
        _save_application_sync, application_id, profile_id, job, kit
    )
    return ApplicationKitResponse(
        application_id=application_id,
        job=job,
        kit=kit,
        created_at=datetime.fromisoformat(created),
    )


def _get_application_sync(application_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()


async def get_application(application_id: str) -> ApplicationKitResponse | None:
    row = await asyncio.to_thread(_get_application_sync, application_id)
    if row is None:
        return None
    return ApplicationKitResponse(
        application_id=row["id"],
        job=JobPosting.model_validate_json(row["job_json"]),
        kit=ApplicationKit.model_validate_json(row["kit_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
