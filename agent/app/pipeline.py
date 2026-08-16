"""End-to-end search flow.

    profile + criteria
        -> search plan (LLM)
        -> collect from sources (parallel)
        -> dedupe + hard filters (rules)
        -> pre-ranking (rules)
        -> fit scoring (LLM, batched)
        -> ranked results

A failing source does not stop the search; the error is reported to the user in
`stats.source_errors`.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .config import get_settings
from .match.scorer import score_jobs
from .schemas import (
    CandidateProfile,
    JobMatch,
    JobPosting,
    SearchCriteria,
    SearchPlan,
    SearchStats,
)
from .search.planner import build_plan
from .search.prefilter import dedupe, hard_filter, rank
from .sources.base import USER_AGENT, JobSource
from .sources.registry import enabled_sources

logger = logging.getLogger(__name__)


async def _fetch_one(
    source: JobSource,
    client: httpx.AsyncClient,
    plan: SearchPlan,
    criteria: SearchCriteria,
    limit: int,
) -> tuple[str, list[JobPosting], str | None]:
    try:
        jobs = await source.fetch(client, plan, criteria, limit)
        return source.name, jobs, None
    except httpx.HTTPStatusError as exc:
        return source.name, [], f"HTTP {exc.response.status_code}"
    except httpx.TimeoutException:
        return source.name, [], "timeout"
    except Exception as exc:  # noqa: BLE001 - a source error must not stop the search
        logger.warning("Source error %s: %s", source.name, exc)
        return source.name, [], str(exc)[:200]


async def collect_jobs(
    plan: SearchPlan, criteria: SearchCriteria
) -> tuple[list[JobPosting], list[str], dict[str, str]]:
    settings = get_settings()
    sources = enabled_sources()

    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        results = await asyncio.gather(
            *(
                _fetch_one(s, client, plan, criteria, settings.fetch_limit_per_source)
                for s in sources
            )
        )

    jobs: list[JobPosting] = []
    used: list[str] = []
    errors: dict[str, str] = {}
    for name, source_jobs, error in results:
        if error:
            errors[name] = error
            continue
        if source_jobs:
            used.append(name)
            jobs.extend(source_jobs)
    return jobs, used, errors


def candidate_places(profile: CandidateProfile, criteria: SearchCriteria) -> list[str]:
    """Geographies the candidate can apply to.

    Whatever the criteria state explicitly, plus the location parsed from the CV.
    Used when ranking geo-restricted remote postings ("Remote — United States").
    """
    places = [*criteria.countries, *criteria.cities]
    if profile.location:
        # "Istanbul, Turkey" -> ["Istanbul", "Turkey"]
        places.extend(part.strip() for part in profile.location.split(",") if part.strip())
    return [p for p in places if p]


async def run_search(
    profile: CandidateProfile, criteria: SearchCriteria
) -> tuple[SearchPlan, SearchStats, list[JobMatch]]:
    started = time.perf_counter()
    settings = get_settings()

    plan = await build_plan(profile, criteria)

    jobs, used, errors = await collect_jobs(plan, criteria)
    stats = SearchStats(fetched=len(jobs), sources_used=used, source_errors=errors)

    unique = dedupe(jobs)
    stats.after_dedupe = len(unique)

    filtered = hard_filter(unique, criteria, plan)
    # If the hard filters removed everything (e.g. a country no source covers),
    # fall back to the deduped pool: a weak result beats an empty screen. But
    # RECORD IT IN STATS — if the user sees results outside their criteria, they
    # need to know why.
    if not filtered and unique:
        logger.info("Hard filters removed every posting, relaxing constraints")
        filtered = unique
        stats.relaxed = True
    stats.after_prefilter = len(filtered)

    ranked = rank(
        filtered, plan, criteria, settings.llm_score_limit, candidate_places(profile, criteria)
    )
    matches = await score_jobs(profile, criteria, ranked)
    stats.llm_scored = sum(1 for m in matches if m.scored_by == "llm")

    matches = matches[: max(1, criteria.max_results)]
    stats.duration_ms = int((time.perf_counter() - started) * 1000)
    return plan, stats, matches
