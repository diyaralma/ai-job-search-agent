"""Kaynak katmanını LLM olmadan test eder.

Anthropic anahtarı olmadan çalışır: sabit bir arama planı kullanır, tüm
kaynaklardan ilan çeker, tekilleştirme ve ön elemenin sonucunu yazar.
Yeni bir kaynak eklerken ya da bir kaynağın API'si değiştiğinde ilk bakılacak yer.

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
    rationale="Smoke testi için sabit plan.",
)

CRITERIA = SearchCriteria(
    work_modes=["remote"],
    seniority=["mid", "senior"],
    posted_within_days=60,
    max_results=20,
)


async def main() -> int:
    jobs, used, errors = await collect_jobs(PLAN, CRITERIA)
    print(f"çekilen ilan       : {len(jobs)}")
    print(f"çalışan kaynaklar  : {', '.join(used) or '-'}")
    if errors:
        for name, err in errors.items():
            print(f"  ! {name}: {err}")

    unique = dedupe(jobs)
    filtered = hard_filter(unique, CRITERIA, PLAN)
    ranked = rank(filtered, PLAN, CRITERIA, 10)

    print(f"tekilleştirme sonrası: {len(unique)}")
    print(f"sert filtre sonrası  : {len(filtered)}")
    print("\nkural skoruna göre ilk 10:")
    for job, score in ranked:
        flag = f"[{job.ats}]" if job.ats else f"[{job.source}]"
        print(f"  {score:5.1f} {flag:<12} {job.title[:52]:<52} @ {job.company[:24]}")

    if not jobs:
        print("\nHİÇ İLAN ÇEKİLEMEDİ — kaynak katmanında sorun var.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
