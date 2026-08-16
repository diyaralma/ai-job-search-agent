"""Rule-based dedupe, hard filters and pre-scoring.

The point is to make the LLM cheap: sources can return hundreds of postings and
sending all of them to the model is both expensive and pointless. Here we drop
the obvious mismatches, roughly rank the rest and hand the most promising N to
the LLM.

The score here is NOT the final score — it only establishes an order. The final
verdict and its justification come from the LLM.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..schemas import JobPosting, SearchCriteria, SearchPlan
from ..text import normalize, term_in

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "principal", "executive"]
SENIORITY_HINTS = {
    "intern": ("intern", "stajyer", "internship", "working student", "werkstudent"),
    "junior": ("junior", "entry level", "entry-level", "graduate", "jr.", "associate"),
    "senior": ("senior", "sr.", "kıdemli"),
    "lead": ("lead", "staff", "team lead", "tech lead", "takım lideri"),
    "principal": ("principal", "architect", "distinguished"),
    "executive": ("head of", "director", "vp ", "chief", "cto", "cpo", "genel müdür"),
}


#: "Remote" postings that are genuinely open to any geography
_GLOBAL_REMOTE = ("anywhere", "worldwide", "global", "any location", "fully remote")
#: "Remote work" words that appear in the location field (Turkish included, since
#: Turkish postings are matched too). They are stripped when computing the geo
#: restriction: "Evden çalışmak" is not a place name so there is no restriction,
#: while "Home Office, Berlin" is limited to Berlin.
_REMOTE_WORDS = frozenset(
    {"remote", "uzaktan", "evden", "calismak", "calisma", "home", "office",
     "telecommute", "wfh", "hybrid", "hibrit", "work", "from"}
)
#: Words denoting a region rather than a country. We do not try to resolve them —
#: "EMEA" includes Turkey, "Europe" is arguable; rather than filter wrongly we
#: treat the restriction as unknown and leave the call to the LLM.
_REGION_WORDS = ("emea", "europe", "european", "apac", "latam", "americas", "eu", "cet", "est", "pst")


def remote_restriction(job: JobPosting) -> str | None:
    """Geo restriction of a remote posting; None if absent or unresolvable.

    "Remote — United States" is not actually open to everyone, it is limited to
    the US. This single source of truth is used by both the hard filter and the
    ranking so the two cannot drift apart.
    """
    if job.work_mode != "remote":
        return None
    loc = normalize(job.location)
    if not loc or any(term_in(loc, g) for g in _GLOBAL_REMOTE):
        return None  # "Worldwide"/"Anywhere" — no restriction
    rest = " ".join(w for w in loc.split() if w not in _REMOTE_WORDS).strip()
    if not rest:
        return None  # just "Remote"/"Evden çalışmak" — no restriction stated
    if any(term_in(rest, r) for r in _REGION_WORDS):
        return None  # region name — cannot resolve reliably, so do not filter
    return rest


def remote_scope_allows(job: JobPosting, places: list[str]) -> bool:
    """Is this remote posting open to applicants from the given places?"""
    restriction = remote_restriction(job)
    if restriction is None:
        return True
    return any(term_in(restriction, p) for p in places if p)


def remote_geo_penalty(job: JobPosting, candidate_places: list[str]) -> float:
    """Pushes remote postings closed to the candidate's geography down the list.

    If the user set no location the hard filter never runs; this penalty keeps
    unreachable postings out of the top slots in that case too.
    """
    if job.work_mode != "remote":
        return 0.0
    return 0.0 if remote_scope_allows(job, candidate_places) else -15.0


def title_seniority(title: str) -> str | None:
    low = f" {title.casefold()} "
    for level, hints in SENIORITY_HINTS.items():
        if any(h in low for h in hints):
            return level
    return None


def dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    """Collapses copies of the same posting coming from different sources.

    For the same (company, title) pair we prefer the record from the employer's
    own ATS board: the link is stable, the description complete and the
    application form automatable.
    """
    best: dict[tuple[str, str], JobPosting] = {}
    for job in jobs:
        key = (normalize(job.company), normalize(job.title))
        current = best.get(key)
        if current is None:
            best[key] = job
            continue
        current_rank = (bool(current.ats), len(current.description))
        new_rank = (bool(job.ats), len(job.description))
        if new_rank > current_rank:
            best[key] = job
    return list(best.values())


def _location_ok(job: JobPosting, criteria: SearchCriteria) -> bool:
    modes = set(criteria.work_modes or ["remote", "hybrid", "onsite"])
    if job.work_mode != "unknown" and job.work_mode not in modes:
        return False

    places = [*criteria.cities, *criteria.countries]
    if not places:
        return True

    if job.work_mode == "remote":
        # A remote posting does not automatically satisfy the user's country:
        # "Berlin remote" or "Remote - USA" are limited to that geography in
        # practice. Only unrestricted ones, or ones covering the user's
        # geography, pass.
        return remote_scope_allows(job, places)

    haystack = normalize(f"{job.location} {job.title}")
    if not haystack.strip():
        # No location information: leave it to the LLM instead of filtering
        return True
    # term_in is required: a plain substring search finds the country "us" inside "Houston"
    return any(term_in(haystack, p) for p in places)


def _fresh_enough(job: JobPosting, criteria: SearchCriteria) -> bool:
    if job.posted_at is None or criteria.posted_within_days <= 0:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=criteria.posted_within_days)
    return job.posted_at >= cutoff


def hard_filter(jobs: list[JobPosting], criteria: SearchCriteria, plan: SearchPlan) -> list[JobPosting]:
    excluded_companies = {normalize(c) for c in criteria.exclude_companies if c}
    excluded_terms = [t.casefold() for t in (*criteria.exclude_keywords, *plan.exclude_terms) if t]

    kept: list[JobPosting] = []
    for job in jobs:
        if not job.title or not job.url:
            continue
        if normalize(job.company) in excluded_companies:
            continue
        title_low = job.title.casefold()
        if any(term in title_low for term in excluded_terms):
            continue
        if not _location_ok(job, criteria):
            continue
        if not _fresh_enough(job, criteria):
            continue
        kept.append(job)
    return kept


def prefilter_score(
    job: JobPosting,
    plan: SearchPlan,
    criteria: SearchCriteria,
    candidate_places: list[str] | None = None,
) -> float:
    """Rough 0-100 fit score."""
    score = 0.0
    title_norm = normalize(job.title)
    body_norm = normalize(f"{job.title} {' '.join(job.tags)} {job.description[:4000]}")

    # Title match is the strongest signal
    for title in plan.titles:
        t = normalize(title)
        if not t:
            continue
        if term_in(title_norm, t):
            score += 22
            break
        # Partial credit if most of the title words appear
        words = [w for w in t.split() if len(w) > 2]
        if words and sum(term_in(title_norm, w) for w in words) / len(words) >= 0.6:
            score += 12
            break

    must = [s for s in plan.must_have_skills if s]
    if must:
        hits = sum(1 for s in must if term_in(body_norm, s))
        score += 34 * (hits / len(must))

    nice = [s for s in plan.nice_to_have_skills if s]
    if nice:
        hits = sum(1 for s in nice if term_in(body_norm, s))
        score += 12 * (hits / len(nice))

    for query in plan.queries:
        if term_in(body_norm, query):
            score += 4

    # Seniority fit
    wanted_levels = set(criteria.seniority)
    level = title_seniority(job.title)
    if wanted_levels and level:
        if level in wanted_levels:
            score += 8
        else:
            distance = abs(SENIORITY_ORDER.index(level) - min(
                SENIORITY_ORDER.index(w) for w in wanted_levels if w in SENIORITY_ORDER
            ))
            score -= min(18, distance * 7)

    # Freshness
    if job.posted_at:
        age_days = (datetime.now(timezone.utc) - job.posted_at).days
        if age_days <= 7:
            score += 8
        elif age_days <= 21:
            score += 4

    # The employer's own board: valuable for application automation
    if job.ats:
        score += 5
    # A posting with no description is worthless to the LLM too
    if len(job.description) < 200:
        score -= 10

    # Push down geo-restricted remote postings the candidate cannot apply to
    score += remote_geo_penalty(job, candidate_places or [])

    return max(0.0, min(100.0, score))


#: Below this threshold a posting is not worth sending to the LLM (no signal hit)
MIN_RELEVANCE = 18.0
#: But let at least this many through so the results screen is never empty
MIN_CANDIDATES = 10
#: A single source may take at most this share of the LLM budget.
#: Why: ATS boards return much longer, richer posting text, which gives them a
#: structural advantage in pre-filtering. Without a cap, a handful of tracked
#: companies fill every slot and suitable postings from other sources are never
#: evaluated. Guaranteeing diversity improves result quality.
MAX_SOURCE_SHARE = 0.5


def rank(
    jobs: list[JobPosting],
    plan: SearchPlan,
    criteria: SearchCriteria,
    limit: int,
    candidate_places: list[str] | None = None,
) -> list[tuple[JobPosting, float]]:
    scored = [(job, prefilter_score(job, plan, criteria, candidate_places)) for job in jobs]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    relevant = [pair for pair in scored if pair[1] >= MIN_RELEVANCE]
    if len(relevant) < MIN_CANDIDATES:
        relevant = scored[:MIN_CANDIDATES]

    return _apply_source_cap(relevant, limit)


def _apply_source_cap(
    scored: list[tuple[JobPosting, float]], limit: int
) -> list[tuple[JobPosting, float]]:
    """Breaks a single source's dominance while preserving score order.

    Takes everything within quota first; if the quota leaves the list short, it
    appends the rest in score order — we never give up result count.
    """
    if limit <= 0:
        return []
    quota = max(1, int(limit * MAX_SOURCE_SHARE))

    picked: list[tuple[JobPosting, float]] = []
    overflow: list[tuple[JobPosting, float]] = []
    counts: dict[str, int] = {}

    for pair in scored:
        source = pair[0].source
        if counts.get(source, 0) < quota:
            counts[source] = counts.get(source, 0) + 1
            picked.append(pair)
            if len(picked) == limit:
                return picked
        else:
            overflow.append(pair)

    picked.extend(overflow[: limit - len(picked)])
    return picked
