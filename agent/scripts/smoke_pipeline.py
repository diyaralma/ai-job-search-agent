"""Tüm pipeline'ı Anthropic anahtarı OLMADAN uçtan uca test eder.

LLM çağrılarını (`structured`) sahte yanıtlarla değiştirip planlayıcı,
kaynaklar, eleme, skorlama, depolama ve API sözleşmesinin doğru
kablolandığını doğrular. Gerçek model kalitesini ölçmez — onun için
anahtar tanımlayıp uygulamayı normal çalıştırın.

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
    headline="Backend developer, 5 yıl Python/Django",
    email="ayse@example.com",
    phone="",
    location="İstanbul, Türkiye",
    years_experience=5,
    seniority="senior",
    target_titles=["Backend Engineer", "Python Developer", "Software Engineer"],
    skills=["Python", "Django", "PostgreSQL", "Kafka", "Docker", "Kubernetes", "AWS"],
    soft_skills=["Mentorluk", "Teknik yazım"],
    languages=["Türkçe (anadil)", "İngilizce (C1)"],
    industries=["E-ticaret", "Teslimat"],
    education=["BSc Bilgisayar Mühendisliği - Boğaziçi Üniversitesi (2019)"],
    certifications=[],
    experience=[
        Experience(
            title="Senior Backend Developer",
            company="Trendyol",
            start="2022-03",
            end="present",
            highlights=["Sipariş servisini mikroservise taşıdı"],
        )
    ],
    summary="Beş yıllık deneyimli, mikroservis ve olay tabanlı mimaride güçlü backend geliştirici.",
)

PLAN = SearchPlan(
    queries=["python backend", "django", "backend engineer"],
    titles=["Backend Engineer", "Python Developer", "Software Engineer"],
    must_have_skills=["Python"],
    nice_to_have_skills=["Django", "PostgreSQL", "Docker", "AWS", "Kubernetes"],
    exclude_terms=["principal", "director", "sales"],
    locations=["remote", "İstanbul"],
    rationale="Sahte plan: senior Python/Django profiline uzaktan backend rolleri aranıyor.",
)


async def fake_structured(*, schema, system, prompt, timeout=None):
    """LLM yerine geçen sahte üretici."""
    if schema is SearchPlan:
        return PLAN

    if schema is ScoredBatch:
        # Prompt içindeki 'id: <job_id>' satırlarını yakalayıp her biri için skor üret
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
                    reasons=["Sahte gerekçe: profil ile teknoloji yığını örtüşüyor."],
                    risks=[] if index % 3 else ["Sahte risk: lokasyon net değil."],
                )
            )
        # Bir ilanı kasten atlıyoruz: eksik skor telafisi çalışıyor mu?
        return ScoredBatch(scores=scores[:-1] if len(scores) > 1 else scores)

    raise AssertionError(f"Beklenmeyen şema: {schema}")


async def main() -> int:
    # LLM'i kullanan iki modülü de yamala (her ikisi de ismi doğrudan import ediyor)
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
        f"çekilen/tekil/eleme: {stats.fetched} / {stats.after_dedupe} / {stats.after_prefilter}"
    )
    print(f"llm skorlanan     : {stats.llm_scored}")
    print(f"sonuç             : {len(matches)} eşleşme, {stats.duration_ms} ms")

    await store.save_search("srch_smoke", "prof_smoke", criteria, plan, stats, matches)
    reloaded = await store.get_search("srch_smoke")
    assert reloaded is not None, "arama kaydedilemedi"
    assert len(reloaded.matches) == len(matches), "kaydedilen eşleşme sayısı tutmuyor"
    print(f"depolama turu     : {len(reloaded.matches)} eşleşme geri okundu")

    rules_fallback = sum(1 for m in matches if m.scored_by == "rules")
    print(f"kural yedeği      : {rules_fallback} ilan (atlanan skorlar telafi edildi)")

    print("\nilk 5 sonuç:")
    for m in matches[:5]:
        print(f"  {m.score:3d} {m.verdict:<8} {m.job.title[:48]:<48} @ {m.job.company[:22]}")

    problems = []
    if not matches:
        problems.append("hiç eşleşme üretilmedi")
    if len({m.job.id for m in matches}) != len(matches):
        problems.append("sonuçlarda tekrar eden ilan var")
    if any(m.score < 0 or m.score > 100 for m in matches):
        problems.append("skor 0-100 aralığı dışında")
    if matches != sorted(matches, key=lambda m: (m.score, m.prefilter_score), reverse=True):
        problems.append("sonuçlar skora göre sıralı değil")

    if problems:
        print("\nSORUN:", "; ".join(problems))
        return 1
    print("\nTüm kontroller geçti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
