"""LLM-based job/candidate matching.

Performance note: each batch is a separate model call and its duration is mostly
proportional to the number of tokens GENERATED. That is why batches are kept
small and run in parallel — 32 postings / batches of 8 / 4 concurrent = one wave.
Larger batches mean fewer calls but longer ones, which makes wall-clock worse.
"""

from __future__ import annotations

import asyncio
import json
import logging

from ..config import get_settings
from ..llm import structured
from ..schemas import (
    CandidateProfile,
    JobMatch,
    JobPosting,
    ScoredBatch,
    SearchCriteria,
)

logger = logging.getLogger(__name__)

SYSTEM = """You are a senior technical recruiter. You are given a candidate profile
and a list of job postings. Rate the candidate's fit for every posting.

Scoring scale:
- 85-100 (strong): The candidate meets the core requirements; level and location
  line up. A strong applicant.
- 65-84 (good): Most requirements are met, 1-2 gaps that can be compensated for.
- 40-64 (stretch): Serious gaps, but there is transferable experience. Worth a
  try, low odds.
- 0-39 (poor): Field, level or location are fundamentally mismatched.

Rules:
- Rely only on the given posting text and profile; never invent a requirement
  that is not in the posting.
- If the posting text is thin, say so in risks and score conservatively.
- Take level mismatch seriously: a "staff engineer" posting cannot be strong for
  a candidate with 2 years of experience.
- Location / work-mode mismatch (e.g. candidate wants remote, posting is onsite
  in another country) drops the score sharply.
- Write AT MOST 2 short bullets in reasons and at most 2 in risks. Keep them
  terse — no long justifications.
- Produce exactly one score object for EVERY posting you are given; copy the
  job_ids verbatim, never invent them.
- Do not inflate scores. If every posting in a list is "strong", the evaluation
  is useless.

Produce only the requested JSON, no other commentary."""


def _context_block(profile: CandidateProfile, criteria: SearchCriteria) -> str:
    return (
        "CANDIDATE PROFILE:\n"
        + json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
        + "\n\nCANDIDATE'S CRITERIA:\n"
        + json.dumps(criteria.model_dump(), ensure_ascii=False, indent=2)
    )


def _fallback_match(job: JobPosting, prefilter: float) -> JobMatch:
    """Fall back to the rule score if the LLM produced nothing — never lose a result."""
    score = int(round(prefilter))
    if score >= 70:
        verdict = "good"
    elif score >= 45:
        verdict = "stretch"
    else:
        verdict = "poor"
    return JobMatch(
        job=job,
        score=score,
        verdict=verdict,
        reasons=["This posting was scored by rules only (no LLM score available)."],
        prefilter_score=prefilter,
        scored_by="rules",
    )


async def _score_batch(
    batch: list[tuple[JobPosting, float]],
    context: str,
    semaphore: asyncio.Semaphore,
) -> list[JobMatch]:
    jobs = {job.id: (job, pre) for job, pre in batch}
    listing = "\n\n---\n\n".join(job.digest() for job, _ in batch)
    prompt = (
        f"{context}\n\n"
        f"Evaluate the following {len(batch)} postings for this candidate. "
        "Produce one score object per posting.\n\n"
        f"POSTINGS:\n\n{listing}"
    )

    async with semaphore:
        try:
            result = await structured(schema=ScoredBatch, system=SYSTEM, prompt=prompt)
        except Exception as exc:  # noqa: BLE001 - one failed batch must not stop the search
            logger.warning("Scoring batch failed (%d postings): %s", len(batch), exc)
            return [_fallback_match(job, pre) for job, pre in batch]

    matches: list[JobMatch] = []
    seen: set[str] = set()
    for score in result.scores:
        entry = jobs.get(score.job_id)
        if entry is None or score.job_id in seen:
            continue  # hallucinated / duplicate id
        seen.add(score.job_id)
        job, pre = entry
        matches.append(
            JobMatch(
                job=job,
                score=max(0, min(100, score.score)),
                verdict=score.verdict,
                matched_skills=score.matched_skills,
                missing_skills=score.missing_skills,
                reasons=score.reasons,
                risks=score.risks,
                prefilter_score=pre,
                scored_by="llm",
            )
        )

    # Do not lose a posting the model skipped
    for job_id, (job, pre) in jobs.items():
        if job_id not in seen:
            matches.append(_fallback_match(job, pre))
    return matches


async def score_jobs(
    profile: CandidateProfile,
    criteria: SearchCriteria,
    ranked: list[tuple[JobPosting, float]],
) -> list[JobMatch]:
    if not ranked:
        return []

    settings = get_settings()
    context = _context_block(profile, criteria)

    size = max(1, settings.score_batch_size)
    batches = [ranked[i : i + size] for i in range(0, len(ranked), size)]
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    logger.info("Scoring %d postings in %d batches", len(ranked), len(batches))
    results = await asyncio.gather(
        *(_score_batch(batch, context, semaphore) for batch in batches)
    )

    matches = [m for group in results for m in group]
    matches.sort(key=lambda m: (m.score, m.prefilter_score), reverse=True)
    return matches
