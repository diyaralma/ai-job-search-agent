"""Kural bazlı tekilleştirme, sert filtreler ve ön skorlama.

Amaç LLM'i ucuzlatmak: kaynaklardan yüzlerce ilan gelebilir, hepsini modele
göndermek hem pahalı hem gereksiz. Burada belirgin uyumsuzları eliyor,
kalanları kabaca sıralayıp en umut verici N tanesini LLM'e bırakıyoruz.

Buradaki skor NİHAİ skor değil — sadece sıraya sokma amaçlı. Nihai karar ve
gerekçe LLM tarafında üretiliyor.
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


#: "Remote" ama coğrafyası herkese açık olan ilanlar
_GLOBAL_REMOTE = ("anywhere", "worldwide", "global", "any location", "fully remote")
#: Lokasyon alanında geçen "uzaktan çalışma" sözcükleri. Coğrafi kısıt
#: hesaplanırken atılıyorlar: "Evden çalışmak" bir yer adı değil, kısıt yok
#: demek; "Home Office, Berlin" ise Berlin ile sınırlı.
_REMOTE_WORDS = frozenset(
    {"remote", "uzaktan", "evden", "calismak", "calisma", "home", "office",
     "telecommute", "wfh", "hybrid", "hibrit", "work", "from"}
)
#: Ülke değil bölge belirten sözcükler. Bunları çözmeye çalışmıyoruz —
#: "EMEA" Türkiye'yi kapsar, "Europe" tartışmalı; yanlış eleme yapmaktansa
#: kısıtı bilinmiyor sayıp kararı LLM'e bırakıyoruz.
_REGION_WORDS = ("emea", "europe", "european", "apac", "latam", "americas", "eu", "cet", "est", "pst")


def remote_restriction(job: JobPosting) -> str | None:
    """Uzaktan ilanın coğrafi kısıtı; kısıt yoksa/çözülemiyorsa None.

    "Remote — United States" gerçekte her yerden başvurulabilir bir ilan değil,
    ABD'yle sınırlı. Buradaki tek doğru kaynak hem sert filtre hem sıralama
    tarafından kullanılıyor ki iki yerde farklı davranış oluşmasın.
    """
    if job.work_mode != "remote":
        return None
    loc = normalize(job.location)
    if not loc or any(term_in(loc, g) for g in _GLOBAL_REMOTE):
        return None  # "Worldwide"/"Anywhere" — kısıt yok
    rest = " ".join(w for w in loc.split() if w not in _REMOTE_WORDS).strip()
    if not rest:
        return None  # sadece "Remote"/"Evden çalışmak" — kısıt belirtilmemiş
    if any(term_in(rest, r) for r in _REGION_WORDS):
        return None  # bölge adı — güvenilir şekilde çözemiyoruz, elemiyoruz
    return rest


def remote_scope_allows(job: JobPosting, places: list[str]) -> bool:
    """Uzaktan ilan, verilen coğrafyalardan başvuruya açık mı?"""
    restriction = remote_restriction(job)
    if restriction is None:
        return True
    return any(term_in(restriction, p) for p in places if p)


def remote_geo_penalty(job: JobPosting, candidate_places: list[str]) -> float:
    """Adayın coğrafyasına kapalı uzaktan ilanları sıralamada aşağı çeker.

    Kullanıcı lokasyon belirtmediyse sert filtre devreye girmiyor; bu ceza
    o durumda da ulaşılamayacak ilanların üst sıraları doldurmasını engelliyor.
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
    """Aynı ilanın farklı kaynaklardaki kopyalarını teke indirir.

    Aynı (şirket, unvan) çiftinde işverenin kendi ATS panosundan gelen kaydı
    tercih ediyoruz: link kalıcı, açıklama tam ve başvuru formu otomatikleştirilebilir.
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
        # Uzaktan ilan kullanıcının ülkesini otomatik karşılamaz: "Berlin remote"
        # ya da "Remote - USA" pratikte o coğrafyayla sınırlı. Yalnızca kısıtsız
        # olanlar veya kullanıcının coğrafyasını kapsayanlar geçer.
        return remote_scope_allows(job, places)

    haystack = normalize(f"{job.location} {job.title}")
    if not haystack.strip():
        # Lokasyon bilgisi yok: elemek yerine LLM'e bırak
        return True
    # term_in şart: düz alt-dize araması "us" ülkesini "Houston" içinde bulur
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
    """0-100 arası kaba uyum skoru."""
    score = 0.0
    title_norm = normalize(job.title)
    body_norm = normalize(f"{job.title} {' '.join(job.tags)} {job.description[:4000]}")

    # Unvan eşleşmesi en güçlü sinyal
    for title in plan.titles:
        t = normalize(title)
        if not t:
            continue
        if term_in(title_norm, t):
            score += 22
            break
        # Unvan kelimelerinin çoğu geçiyorsa kısmi puan
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

    # Seviye uyumu
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

    # Tazelik
    if job.posted_at:
        age_days = (datetime.now(timezone.utc) - job.posted_at).days
        if age_days <= 7:
            score += 8
        elif age_days <= 21:
            score += 4

    # İşverenin kendi panosu: başvuru otomasyonu için değerli
    if job.ats:
        score += 5
    # Açıklaması olmayan ilan LLM için de değersiz
    if len(job.description) < 200:
        score -= 10

    # Adayın başvuramayacağı coğrafi kısıtlı uzaktan ilanları aşağı çek
    score += remote_geo_penalty(job, candidate_places or [])

    return max(0.0, min(100.0, score))


#: Bu eşiğin altındaki ilan LLM'e gönderilmeye değmez (hiçbir sinyali tutmuyor)
MIN_RELEVANCE = 18.0
#: Ama sonuç ekranını tamamen boş bırakmamak için en az bu kadarını yine de geçir
MIN_CANDIDATES = 10
#: Tek bir kaynak LLM bütçesinin en fazla bu kadarını alabilir.
#: Gerekçe: ATS panoları çok daha uzun ve zengin ilan metni döndürüyor, bu da
#: onlara ön elemede yapısal avantaj veriyor. Sınır olmadan takip edilen birkaç
#: şirket tüm sonuçları dolduruyor ve diğer kaynaklardaki uygun ilanlar hiç
#: değerlendirilmiyor. Çeşitliliği garanti etmek sonucun kalitesini artırıyor.
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
    """Skor sırasını koruyarak tek kaynağın baskınlığını kırar.

    Önce kotayı aşmayanları alır; kota yüzünden liste dolmazsa kalanları
    yine skor sırasıyla ekler — sonuç sayısından ödün vermiyoruz.
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
