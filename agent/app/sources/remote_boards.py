"""Anahtar gerektirmeyen açık iş panoları.

Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas — hepsi ücretsiz ve herkese
açık; MVP'nin varsayılan kaynakları bunlar. Remotive ve Jobicy sunucu tarafında
arama destekliyor, diğerlerinde filtreleme istemci tarafında yapılıyor.

Jobicy ve Himalayas ayrıca **coğrafi kısıtı yapılandırılmış** veriyor
(`jobGeo` / `locationRestrictions`). Bunu `location` alanına taşıyoruz ki
prefilter'daki `remote_restriction()` mantığı tahmin yürütmeden çalışsın:
"Remote — United States" ilanı Türkiye'deki adaya gösterilmesin.
"""

from __future__ import annotations

import httpx

from ..schemas import JobPosting, SearchCriteria, SearchPlan
from ..text import matches_any as _matches_any
from .base import USER_AGENT, JobSource, detect_work_mode, make_id, parse_date, strip_html


class RemotiveSource(JobSource):
    name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()
        # Remotive'in arama motoru dar eşleşiyor: tek sorgu az sonuç veriyor,
        # bu yüzden planın sorgularının çoğunu ayrı ayrı deniyoruz.
        queries = (plan.queries or [""])[:6]
        per_query = max(25, limit // max(1, len(queries)))

        for query in queries:
            params = {"limit": per_query}
            if query:
                params["search"] = query
            resp = await client.get(self.URL, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                ext = str(item.get("id"))
                if ext in seen:
                    continue
                seen.add(ext)
                description = strip_html(item.get("description"))
                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=item.get("title", "").strip(),
                        company=(item.get("company_name") or "").strip(),
                        location=item.get("candidate_required_location") or "Remote",
                        work_mode="remote",
                        employment_type=item.get("job_type") or "",
                        description=description,
                        url=item.get("url", ""),
                        salary_text=item.get("salary") or "",
                        posted_at=parse_date(item.get("publication_date")),
                        tags=[t for t in (item.get("tags") or []) if t],
                    )
                )
            if len(out) >= limit:
                break
        return out[:limit]


class ArbeitnowSource(JobSource):
    """Ağırlıklı olarak Avrupa (özellikle Almanya) ilanları."""

    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        # Arbeitnow'da sunucu tarafı arama yok: tüm panoyu sayfalayıp istemcide
        # filtreliyoruz. Az sayfa çekmek alakalı ilanları tamamen kaçırdırıyor.
        terms = list({*plan.queries, *plan.titles, *plan.must_have_skills})
        out: list[JobPosting] = []

        for page in range(1, 9):
            resp = await client.get(
                self.URL, params={"page": page}, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                break
            for item in data:
                title = (item.get("title") or "").strip()
                description = strip_html(item.get("description"))
                tags = [t for t in (item.get("tags") or []) if t]
                haystack = " ".join([title, " ".join(tags), description[:1500]])
                if not _matches_any(haystack, terms):
                    continue
                ext = item.get("slug") or item.get("url", "")
                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=title,
                        company=(item.get("company_name") or "").strip(),
                        location=item.get("location") or "",
                        work_mode="remote" if item.get("remote") else detect_work_mode(
                            item.get("location"), description[:800]
                        ),
                        employment_type=", ".join(item.get("job_types") or []),
                        description=description,
                        url=item.get("url", ""),
                        posted_at=parse_date(item.get("created_at")),
                        tags=tags,
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class RemoteOKSource(JobSource):
    name = "remoteok"
    URL = "https://remoteok.com/api"

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        resp = await client.get(self.URL, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []

        terms = list({*plan.queries, *plan.titles, *plan.must_have_skills})
        out: list[JobPosting] = []
        for item in payload:
            # İlk eleman yasal uyarı nesnesi; ilan alanları yoksa atla
            if not isinstance(item, dict) or not item.get("position"):
                continue
            title = (item.get("position") or "").strip()
            description = strip_html(item.get("description"))
            tags = [t for t in (item.get("tags") or []) if t]
            if not _matches_any(" ".join([title, " ".join(tags), description[:1500]]), terms):
                continue

            salary_min, salary_max = item.get("salary_min"), item.get("salary_max")
            salary_text = ""
            if salary_min and salary_max:
                salary_text = f"${int(salary_min):,} - ${int(salary_max):,}"

            ext = str(item.get("id") or item.get("slug"))
            out.append(
                JobPosting(
                    id=make_id(self.name, ext),
                    source=self.name,
                    external_id=ext,
                    title=title,
                    company=(item.get("company") or "").strip(),
                    location=item.get("location") or "Remote",
                    work_mode="remote",
                    description=description,
                    url=item.get("url") or item.get("apply_url") or "",
                    salary_text=salary_text,
                    posted_at=parse_date(item.get("epoch") or item.get("date")),
                    tags=tags,
                )
            )
            if len(out) >= limit:
                break
        return out


class JobicySource(JobSource):
    """Uzaktan çalışma ilanları; `jobGeo` alanı coğrafi kısıtı veriyor."""

    name = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    #: jobGeo'da kısıt olmadığını belirten değerler
    _OPEN_GEO = {"", "anywhere", "worldwide", "global"}

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        out: list[JobPosting] = []
        seen: set[str] = set()

        for query in (plan.queries or [""])[:5]:
            params = {"count": 50}
            if query:
                params["tag"] = query
            resp = await client.get(self.URL, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                ext = str(item.get("id") or item.get("jobSlug"))
                if not ext or ext in seen:
                    continue
                seen.add(ext)

                geo = (item.get("jobGeo") or "").strip()
                # Kısıtı location'a taşı: aşağı akıştaki coğrafya filtresi
                # bu metni okuyor.
                location = "Worldwide" if geo.lower() in self._OPEN_GEO else f"Remote - {geo}"

                job_type = item.get("jobType")
                if isinstance(job_type, list):
                    job_type = ", ".join(job_type)

                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=(item.get("jobTitle") or "").strip(),
                        company=(item.get("companyName") or "").strip(),
                        location=location,
                        work_mode="remote",
                        employment_type=job_type or "",
                        description=strip_html(item.get("jobDescription") or item.get("jobExcerpt")),
                        url=item.get("url") or f"https://jobicy.com/jobs/{item.get('jobSlug', '')}",
                        posted_at=parse_date(item.get("pubDate")),
                        tags=[t for t in [item.get("jobIndustry"), item.get("jobLevel")] if t and isinstance(t, str)],
                    )
                )
                if len(out) >= limit:
                    return out
        return out


class HimalayasSource(JobSource):
    """Uzaktan çalışma ilanları; `locationRestrictions` ülke listesi veriyor."""

    name = "himalayas"
    URL = "https://himalayas.app/jobs/api"
    PAGE_SIZE = 20

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        terms = list({*plan.queries, *plan.titles, *plan.must_have_skills})
        out: list[JobPosting] = []
        seen: set[str] = set()

        # Sunucu tarafı arama yok: sayfalayıp istemcide filtreliyoruz.
        for offset in range(0, 8 * self.PAGE_SIZE, self.PAGE_SIZE):
            resp = await client.get(
                self.URL,
                params={"limit": self.PAGE_SIZE, "offset": offset},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            items = resp.json().get("jobs", [])
            if not items:
                break

            for item in items:
                ext = str(item.get("guid") or item.get("applicationLink"))
                if not ext or ext in seen:
                    continue
                seen.add(ext)

                title = (item.get("title") or "").strip()
                description = strip_html(item.get("description") or item.get("excerpt"))
                categories = [c for c in (item.get("categories") or []) if isinstance(c, str)]
                if not _matches_any(f"{title} {' '.join(categories)} {description[:1500]}", terms):
                    continue

                restrictions = [r for r in (item.get("locationRestrictions") or []) if r]
                location = f"Remote - {', '.join(restrictions)}" if restrictions else "Remote"

                min_salary, max_salary = item.get("minSalary"), item.get("maxSalary")
                salary_text = ""
                if min_salary and max_salary:
                    currency = item.get("currency") or ""
                    salary_text = f"{int(min_salary):,} - {int(max_salary):,} {currency}".strip()

                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=title,
                        company=(item.get("companyName") or "").strip(),
                        location=location,
                        work_mode="remote",
                        employment_type=item.get("employmentType") or "",
                        description=description,
                        url=item.get("applicationLink") or "",
                        salary_text=salary_text,
                        posted_at=parse_date(item.get("pubDate")),
                        tags=categories[:6],
                    )
                )
                if len(out) >= limit:
                    return out
        return out
