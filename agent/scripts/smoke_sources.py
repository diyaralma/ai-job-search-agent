"""Tests the source layer without any LLM.

Needs no API key: uses a fixed search plan, fetches postings from every source
and prints what dedupe and pre-filtering produced. The first place to look when
adding a source or when a source's API changes.

    ./.venv/bin/python scripts/smoke_sources.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import collect_jobs  # noqa: E402
from app.schemas import SearchCriteria, SearchPlan  # noqa: E402
from app.search.prefilter import dedupe, hard_filter, rank  # noqa: E402

PLAN = SearchPlan(
    queries=["python backend", "django", "backend engineer"],
    titles=["Backend Engineer", "Python Developer", "Software Engineer"],
    must_have_skills=["Python"],
    nice_to_have_skills=["Django", "PostgreSQL", "Docker", "AWS"],
    exclude_terms=["principal", "director", "sales"],
    locations=["remote"],
    rationale="Fixed plan for the smoke test.",
)

CRITERIA = SearchCriteria(
    work_modes=["remote"],
    seniority=["mid", "senior"],
    posted_within_days=60,
    max_results=20,
)


async def main() -> int:
    jobs, used, errors = await collect_jobs(PLAN, CRITERIA)
    print(f"fetched postings   : {len(jobs)}")
    print(f"working sources    : {', '.join(used) or '-'}")
    if errors:
        for name, err in errors.items():
            print(f"  ! {name}: {err}")

    unique = dedupe(jobs)
    filtered = hard_filter(unique, CRITERIA, PLAN)
    ranked = rank(filtered, PLAN, CRITERIA, 10)

    print(f"after dedupe       : {len(unique)}")
    print(f"after hard filter  : {len(filtered)}")
    print("\ntop 10 by rule score:")
    for job, score in ranked:
        flag = f"[{job.ats}]" if job.ats else f"[{job.source}]"
        print(f"  {score:5.1f} {flag:<12} {job.title[:52]:<52} @ {job.company[:24]}")

    if not jobs:
        print("\nNO POSTINGS FETCHED — something is wrong in the source layer.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
