"""Kural katmanının birim testleri — LLM çağrısı yapmaz, saniyeler sürer.

Buradaki mantık sessizce bozulabilecek türden: bir eşleştirme hatası ilanları
elemez, sadece yanlış sıralar ve fark etmesi zor olur.

    ./.venv/bin/python scripts/test_prefilter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import JobPosting, SearchCriteria, SearchPlan  # noqa: E402
from app.search.prefilter import dedupe, hard_filter, remote_geo_penalty  # noqa: E402
from app.text import matches_any, term_in  # noqa: E402

failures: list[str] = []


def check(name: str, got, expected) -> None:
    if got == expected:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}: {got!r} != beklenen {expected!r}")
        failures.append(name)


def job(**kw) -> JobPosting:
    base = dict(
        id="x", source="s", external_id="e", title="t", company="c",
        location="", work_mode="unknown", url="http://x", description="",
    )
    base.update(kw)
    return JobPosting(**base)


print("term_in — kelime sınırı (alt-dize eşleşmesi skorlamayı çöpe çevirir):")
check("AWS 'laws' içinde eşleşmemeli", term_in("employment laws apply", "AWS"), False)
check("AWS kendi başına eşleşmeli", term_in("experience with aws and gcp", "AWS"), True)
check("çok kelimeli terim", term_in("strong machine learning background", "machine learning"), True)
check("R tek harf, rastgele eşleşmemeli", term_in("python and django", "R"), False)
check("aksan normalize", term_in(term_in.__doc__ and "istanbul turkiye" or "", "Türkiye"), True)

print("\nmatches_any:")
check("boş terim listesi her şeyi geçirir", matches_any("herhangi bir metin", []), True)
check("eşleşme yoksa False", matches_any("sales representative", ["python", "django"]), False)

print("\nremote_geo_penalty — aday İstanbul/Türkiye:")
places = ["İstanbul", "Türkiye"]
cases = [
    ("Remote", "remote", 0.0),
    ("Remote - United States", "remote", -15.0),
    ("Remote, United Kingdom", "remote", -15.0),
    ("Remote - Anywhere", "remote", 0.0),
    ("Remote (Worldwide)", "remote", 0.0),
    ("Remote - EMEA", "remote", 0.0),
    ("Remote - Türkiye", "remote", 0.0),
    ("", "remote", 0.0),
    ("London, UK", "onsite", 0.0),
    # Türkçe uzaktan ifadeleri yer adı değil -> kısıtsız sayılmalı
    ("Evden çalışmak", "remote", 0.0),
    ("Uzaktan", "remote", 0.0),
    ("Home Office, Berlin", "remote", -15.0),
]
for loc, mode, expected in cases:
    check(f"{loc or '(boş)'} [{mode}]", remote_geo_penalty(job(location=loc, work_mode=mode), places), expected)

print("\nhard_filter — kullanıcı Türkiye/Ankara/İstanbul seçtiğinde:")
tr_crit = SearchCriteria(
    countries=["Türkiye"], cities=["Ankara", "İstanbul"],
    work_modes=["remote", "hybrid", "onsite"], posted_within_days=0,
)
loc_cases = [
    ("Berlin", "remote", False, "Berlin remote -> Almanya ile sınırlı, elenmeli"),
    ("Remote - USA", "remote", False, "ABD kısıtlı"),
    ("Remote, Germany", "remote", False, "Almanya kısıtlı"),
    ("Worldwide", "remote", True, "her yerden -> geçmeli"),
    ("Remote", "remote", True, "kısıt belirtilmemiş -> geçmeli"),
    ("Remote - EMEA", "remote", True, "bölge, çözemiyoruz -> geçmeli"),
    ("Remote - Türkiye", "remote", True, "kullanıcının ülkesi"),
    ("İstanbul, Türkiye", "onsite", True, "Türkiye ofis işi"),
    ("Berlin, Germany", "onsite", False, "Almanya ofis işi -> elenmeli"),
]
for loc, mode, expected, desc in loc_cases:
    j = job(location=loc, work_mode=mode, title="Backend Engineer", url="http://x")
    got = len(hard_filter([j], tr_crit, SearchPlan(
        queries=[], titles=[], must_have_skills=[], nice_to_have_skills=[],
        exclude_terms=[], locations=[], rationale="",
    ))) == 1
    check(f"{loc} [{mode}] — {desc}", got, expected)

print("\ndedupe — aynı ilanın kopyaları:")
jobs = [
    job(id="a", source="remotive", company="Acme", title="Backend Engineer", description="x" * 300),
    job(id="b", source="greenhouse", company="Acme", title="Backend Engineer", description="y" * 100, ats="greenhouse"),
    job(id="c", source="remotive", company="Beta", title="Backend Engineer", description="z" * 300),
]
result = dedupe(jobs)
check("2 tekil ilan kalmalı", len(result), 2)
check("ATS kaydı tercih edilmeli", next(j.id for j in result if j.company == "Acme"), "b")

print()
if failures:
    print(f"BAŞARISIZ: {len(failures)} kontrol -> {', '.join(failures)}")
    raise SystemExit(1)
print("Tüm kontroller geçti.")
