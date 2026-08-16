"""LLM ile ilan-aday eşleştirmesi.

Performans notu: her parti ayrı bir Claude Code subprocess'i ve süre büyük
ölçüde ÜRETİLEN token sayısıyla orantılı. Bu yüzden partiler küçük tutulup
paralel çalıştırılıyor — 32 ilan / 8'lik partiler / 4 eşzamanlı = tek dalga.
Parti boyutunu büyütmek çağrı sayısını azaltır ama her çağrıyı uzatır ve
duvar saatini kötüleştirir.
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

SYSTEM = """Sen kıdemli bir teknik işe alım uzmanısın. Sana bir aday profili ve
iş ilanları veriliyor. Her ilan için adayın uygunluğunu değerlendireceksin.

Skorlama ölçütü:
- 85-100 (strong): Aday ilanın çekirdek gereksinimlerini karşılıyor, seviye ve
  lokasyon uyumlu. Başvuru için güçlü aday.
- 65-84 (good): Çoğu gereksinim karşılanıyor, 1-2 eksik var ama telafi edilebilir.
- 40-64 (stretch): Ciddi eksikler var ama transfer edilebilir deneyim mevcut.
  Aday deneyebilir, kabul olasılığı düşük.
- 0-39 (poor): Alan, seviye veya lokasyon temelde uyumsuz.

Kurallar:
- Sadece verilen ilan metnine ve profile dayan; ilanda yazmayan gereksinim uydurma.
- İlan metni eksikse bunu risks alanında belirt ve skoru temkinli ver.
- Seviye uyumsuzluğunu ciddiye al: 2 yıllık bir adaya "staff engineer" ilanı
  strong olamaz.
- Lokasyon/çalışma şekli uyumsuzluğu (ör. aday uzaktan istiyor, ilan ofisten
  ve başka ülkede) skoru sert düşürür.
- reasons alanına EN FAZLA 2 kısa madde yaz, risks alanına en fazla 2. Türkçe
  yaz, teknoloji adları İngilizce kalsın. Uzun gerekçe yazma.
- Sana verilen HER ilan için tam olarak bir skor nesnesi üret; job_id'leri
  verildiği gibi birebir kopyala, uydurma.
- Skorları şişirme. Bir listede her ilan "strong" ise değerlendirme işe yaramaz.

Yalnızca istenen JSON'u üret, başka açıklama yazma."""


def _context_block(profile: CandidateProfile, criteria: SearchCriteria) -> str:
    return (
        "ADAY PROFİLİ:\n"
        + json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
        + "\n\nADAYIN KRİTERLERİ:\n"
        + json.dumps(criteria.model_dump(), ensure_ascii=False, indent=2)
    )


def _fallback_match(job: JobPosting, prefilter: float) -> JobMatch:
    """LLM sonuç üretemezse kural skorunu kullan — sonuç kaybetmeyelim."""
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
        reasons=["Bu ilan yalnızca kural bazlı olarak değerlendirildi (LLM skoru alınamadı)."],
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
        f"Aşağıdaki {len(batch)} ilanı bu aday için değerlendir. "
        "Her ilan için bir skor nesnesi üret.\n\n"
        f"İLANLAR:\n\n{listing}"
    )

    async with semaphore:
        try:
            result = await structured(schema=ScoredBatch, system=SYSTEM, prompt=prompt)
        except Exception as exc:  # noqa: BLE001 - tek parti düşse de arama sürsün
            logger.warning("Skorlama partisi başarısız (%d ilan): %s", len(batch), exc)
            return [_fallback_match(job, pre) for job, pre in batch]

    matches: list[JobMatch] = []
    seen: set[str] = set()
    for score in result.scores:
        entry = jobs.get(score.job_id)
        if entry is None or score.job_id in seen:
            continue  # halüsinasyon / tekrar eden id
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

    # Model bir ilanı atladıysa onu kaybetme
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

    logger.info("%d ilan %d partide skorlanıyor", len(ranked), len(batches))
    results = await asyncio.gather(
        *(_score_batch(batch, context, semaphore) for batch in batches)
    )

    matches = [m for group in results for m in group]
    matches.sort(key=lambda m: (m.score, m.prefilter_score), reverse=True)
    return matches
