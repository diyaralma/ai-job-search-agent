"""Uçtan uca arama akışı.

    profil + kriterler
        -> arama planı (LLM)
        -> kaynaklardan toplama (paralel)
        -> tekilleştirme + sert filtreler (kural)
        -> ön sıralama (kural)
        -> uygunluk skorlaması (LLM, partili + cache'li)
        -> sıralı sonuç

Bir kaynak hata verirse arama durmuyor; hata `stats.source_errors` içinde
kullanıcıya raporlanıyor.
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
        return source.name, [], "zaman aşımı"
    except Exception as exc:  # noqa: BLE001 - kaynak hatası aramayı durdurmasın
        logger.warning("Kaynak hatası %s: %s", source.name, exc)
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
    """Adayın başvurabileceği coğrafyalar.

    Kriterlerde açıkça belirtilenler + CV'den çıkan konum. Coğrafi kısıtlı
    uzaktan ilanları ("Remote — United States") sıralarken kullanılıyor.
    """
    places = [*criteria.countries, *criteria.cities]
    if profile.location:
        # "İstanbul, Türkiye" -> ["İstanbul", "Türkiye"]
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
    # Sert filtreler her şeyi elediyse (ör. hiçbir kaynağın kapsamadığı bir
    # ülke seçilmiş) tekilleştirilmiş havuza geri dön: boş ekran yerine zayıf
    # sonuç göstermek daha yararlı. Ama bunu STATS'A YAZ — kullanıcı kriterine
    # uymayan sonuç görüyorsa nedenini bilmeli.
    if not filtered and unique:
        logger.info("Sert filtreler tüm ilanları eledi, kısıtlar gevşetiliyor")
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
