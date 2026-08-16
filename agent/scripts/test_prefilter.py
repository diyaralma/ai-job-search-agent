"""Unit tests for the rule layer — makes no LLM calls, runs in seconds.

The logic here is the kind that breaks silently: a matching bug does not drop
postings, it just orders them wrongly, which is hard to notice.

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
        print(f"  ✗ {name}: {got!r} != expected {expected!r}")
        failures.append(name)


def job(**kw) -> JobPosting:
    base = dict(
        id="x", source="s", external_id="e", title="t", company="c",
        location="", work_mode="unknown", url="http://x", description="",
    )
    base.update(kw)
    return JobPosting(**base)


print("term_in — word boundaries (substring matching makes scoring worthless):")
check("AWS must not match inside 'laws'", term_in("employment laws apply", "AWS"), False)
check("AWS matches on its own", term_in("experience with aws and gcp", "AWS"), True)
check("multi-word term", term_in("strong machine learning background", "machine learning"), True)
check("single letter R must not match at random", term_in("python and django", "R"), False)
check("accent normalization", term_in(term_in.__doc__ and "istanbul turkiye" or "", "Türkiye"), True)

print("\nmatches_any:")
check("an empty term list passes everything", matches_any("any text at all", []), True)
check("False when nothing matches", matches_any("sales representative", ["python", "django"]), False)

print("\nremote_geo_penalty — candidate in İstanbul/Türkiye:")
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
    # Turkish remote phrases are not place names -> must count as unrestricted
    ("Evden çalışmak", "remote", 0.0),
    ("Uzaktan", "remote", 0.0),
    ("Home Office, Berlin", "remote", -15.0),
]
for loc, mode, expected in cases:
    check(f"{loc or '(empty)'} [{mode}]", remote_geo_penalty(job(location=loc, work_mode=mode), places), expected)

print("\nhard_filter — when the user picks Türkiye/Ankara/İstanbul:")
tr_crit = SearchCriteria(
    countries=["Türkiye"], cities=["Ankara", "İstanbul"],
    work_modes=["remote", "hybrid", "onsite"], posted_within_days=0,
)
loc_cases = [
    ("Berlin", "remote", False, "Berlin remote -> limited to Germany, must be dropped"),
    ("Remote - USA", "remote", False, "US-restricted"),
    ("Remote, Germany", "remote", False, "Germany-restricted"),
    ("Worldwide", "remote", True, "open to anywhere -> must pass"),
    ("Remote", "remote", True, "no restriction stated -> must pass"),
    ("Remote - EMEA", "remote", True, "region, unresolvable -> must pass"),
    ("Remote - Türkiye", "remote", True, "the user's own country"),
    ("İstanbul, Türkiye", "onsite", True, "onsite job in Türkiye"),
    ("Berlin, Germany", "onsite", False, "onsite job in Germany -> must be dropped"),
]
for loc, mode, expected, desc in loc_cases:
    j = job(location=loc, work_mode=mode, title="Backend Engineer", url="http://x")
    got = len(hard_filter([j], tr_crit, SearchPlan(
        queries=[], titles=[], must_have_skills=[], nice_to_have_skills=[],
        exclude_terms=[], locations=[], rationale="",
    ))) == 1
    check(f"{loc} [{mode}] — {desc}", got, expected)

print("\ndedupe — copies of the same posting:")
jobs = [
    job(id="a", source="remotive", company="Acme", title="Backend Engineer", description="x" * 300),
    job(id="b", source="greenhouse", company="Acme", title="Backend Engineer", description="y" * 100, ats="greenhouse"),
    job(id="c", source="remotive", company="Beta", title="Backend Engineer", description="z" * 300),
]
result = dedupe(jobs)
check("2 unique postings must remain", len(result), 2)
check("the ATS record must win", next(j.id for j in result if j.company == "Acme"), "b")

print()
if failures:
    print(f"FAILED: {len(failures)} checks -> {', '.join(failures)}")
    raise SystemExit(1)
print("All checks passed.")
