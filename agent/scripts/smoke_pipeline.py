"""Tests the whole pipeline end to end with NO LLM access.

It replaces the LLM calls (`structured`) with canned answers and verifies that
the planner, sources, filtering, scoring, storage and API contract are wired
correctly. It does not measure real model quality — for that, configure a
provider and run the app normally.

    ./.venv/bin/python scripts/smoke_pipeline.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402
from app.schemas import (  # noqa: E402
    CandidateProfile,
    Experience,
    JobScore,
    ScoredBatch,
    SearchCriteria,
    SearchPlan,
)

PROFILE = CandidateProfile(
    full_name="Ayşe Yılmaz",
    headline="Backend developer, 5 years of Python/Django",
    email="ayse@example.com",
    phone="",
    location="İstanbul, Türkiye",
    years_experience=5,
    seniority="senior",
    target_titles=["Backend Engineer", "Python Developer", "Software Engineer"],
    skills=["Python", "Django", "PostgreSQL", "Kafka", "Docker", "Kubernetes", "AWS"],
    soft_skills=["Mentoring", "Technical writing"],
    languages=["Turkish (native)", "English (C1)"],
    industries=["E-ticaret", "Teslimat"],
    education=["BSc Computer Engineering - Boğaziçi University (2019)"],
    certifications=[],
    experience=[
        Experience(
            title="Senior Backend Developer",
            company="Trendyol",
            start="2022-03",
            end="present",
            highlights=["Moved the order service to microservices"],
        )
    ],
    summary="Backend developer with five years of experience, strong in microservices and event-driven architecture.",
)

PLAN = SearchPlan(
    queries=["python backend", "django", "backend engineer"],
    titles=["Backend Engineer", "Python Developer", "Software Engineer"],
    must_have_skills=["Python"],
    nice_to_have_skills=["Django", "PostgreSQL", "Docker", "AWS", "Kubernetes"],
    exclude_terms=["principal", "director", "sales"],
    locations=["remote", "İstanbul"],
    rationale="Fake plan: looking for remote backend roles for a senior Python/Django profile.",
)


async def fake_structured(*, schema, system, prompt, timeout=None):
    """Stand-in generator that replaces the LLM."""
    if schema is SearchPlan:
        return PLAN

    if schema is ScoredBatch:
        # Grab the 'id: <job_id>' lines from the prompt and score each one
        job_ids = [
            line.split("id:", 1)[1].strip()
            for line in prompt.splitlines()
            if line.startswith("id: ")
        ]
        scores = []
        for index, job_id in enumerate(job_ids):
            raw = 92 - index * 7
            score = max(20, raw)
            verdict = "strong" if score >= 85 else "good" if score >= 65 else "stretch" if score >= 40 else "poor"
            scores.append(
                JobScore(
                    job_id=job_id,
                    score=score,
                    verdict=verdict,
                    matched_skills=["Python", "Docker"],
                    missing_skills=["Go"] if index % 2 else [],
                    reasons=["Fake reason: the profile overlaps with the tech stack."],
                    risks=[] if index % 3 else ["Fake risk: the location is unclear."],
                )
            )
        # Deliberately skip one posting: does the missing-score fallback work?
        return ScoredBatch(scores=scores[:-1] if len(scores) > 1 else scores)

    raise AssertionError(f"Unexpected schema: {schema}")


async def main() -> int:
    # Patch both modules that use the LLM (both import the name directly)
    from app.match import scorer
    from app.search import planner

    planner.structured = fake_structured
    scorer.structured = fake_structured

    from app.pipeline import run_search

    await store.init_db()
    saved = await store.save_profile("prof_smoke", "sample_cv.txt", PROFILE)
    print(f"profil kaydedildi : {saved.profile_id}")

    criteria = SearchCriteria(
        work_modes=["remote"], seniority=["mid", "senior"], posted_within_days=60, max_results=15
    )
    plan, stats, matches = await run_search(PROFILE, criteria)

    print(f"kaynaklar         : {', '.join(stats.sources_used) or '-'}")
    if stats.source_errors:
        for name, err in stats.source_errors.items():
            print(f"  ! {name}: {err}")
    print(
        f"fetched/unique/filtered: {stats.fetched} / {stats.after_dedupe} / {stats.after_prefilter}"
    )
    print(f"llm skorlanan     : {stats.llm_scored}")
    print(f"result            : {len(matches)} matches, {stats.duration_ms} ms")

    await store.save_search("srch_smoke", "prof_smoke", criteria, plan, stats, matches)
    reloaded = await store.get_search("srch_smoke")
    assert reloaded is not None, "arama kaydedilemedi"
    assert len(reloaded.matches) == len(matches), "stored match count does not line up"
    print(f"storage round-trip: {len(reloaded.matches)} matches read back")

    rules_fallback = sum(1 for m in matches if m.scored_by == "rules")
    print(f"rule fallback     : {rules_fallback} postings (skipped scores compensated)")

    print("\ntop 5 results:")
    for m in matches[:5]:
        print(f"  {m.score:3d} {m.verdict:<8} {m.job.title[:48]:<48} @ {m.job.company[:22]}")

    problems = []
    if not matches:
        problems.append("no matches were produced")
    if len({m.job.id for m in matches}) != len(matches):
        problems.append("duplicate postings in the results")
    if any(m.score < 0 or m.score > 100 for m in matches):
        problems.append("score outside the 0-100 range")
    if matches != sorted(matches, key=lambda m: (m.score, m.prefilter_score), reverse=True):
        problems.append("results are not ordered by score")

    if problems:
        print("\nSORUN:", "; ".join(problems))
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
