"""Şirketlerin kendi ATS iş panoları: Greenhouse, Lever, Ashby, Workable.

Bu kaynak iki nedenle önemli:
1. İlan doğrudan işverenden geliyor — aracı yok, ilan taze ve link kalıcı.
2. Başvuru formu bu panolarda açık ve makine tarafından doldurulabilir;
   premium "onaylı otomatik başvuru" akışı yalnızca bu ilanlar üzerinde
   çalışacak (bkz. README, Faz 2).

Takip edilecek şirketler `companies.json` içinde. Bir şirket panosu 404
dönerse o şirket atlanır, diğerleri etkilenmez.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..schemas import JobPosting, SearchCriteria, SearchPlan
from ..text import matches_any
from .base import USER_AGENT, JobSource, detect_work_mode, make_id, parse_date, strip_html

logger = logging.getLogger(__name__)

COMPANIES_FILE = Path(__file__).with_name("companies.json")

#: Tarihi olmayan ilanları sıralamada en sona atmak için
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def load_companies() -> dict[str, list[str]]:
    if not COMPANIES_FILE.exists():
        return {}
    try:
        data = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("companies.json okunamadı, ATS kaynağı boş dönecek")
        return {}
    return {k: [s for s in v if s] for k, v in data.items() if isinstance(v, list)}


def _relevant(job: JobPosting, terms: list[str]) -> bool:
    return matches_any(
        f"{job.title} {' '.join(job.tags)} {job.description[:1500]}", terms
    )


class ATSSource(JobSource):
    name = "ats"

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        companies = load_companies()
        terms = list({*plan.queries, *plan.titles, *plan.must_have_skills})

        tasks = []
        for company in companies.get("greenhouse", []):
            tasks.append(self._greenhouse(client, company))
        for company in companies.get("lever", []):
            tasks.append(self._lever(client, company))
        for company in companies.get("ashby", []):
            tasks.append(self._ashby(client, company))
        for company in companies.get("workable", []):
            tasks.append(self._workable(client, company))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[JobPosting] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.debug("ATS panosu atlandı: %s", result)
                continue
            for job in result:
                if _relevant(job, terms):
                    out.append(job)
        out.sort(key=lambda j: j.posted_at or _EPOCH, reverse=True)
        return out[:limit]

    # -- Greenhouse ---------------------------------------------------------
    async def _greenhouse(self, client: httpx.AsyncClient, board: str) -> list[JobPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
        resp = await client.get(
            url, params={"content": "true"}, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        jobs = []
        for item in resp.json().get("jobs", []):
            ext = f"{board}:{item.get('id')}"
            location = (item.get("location") or {}).get("name", "")
            description = strip_html(item.get("content"))
            jobs.append(
                JobPosting(
                    id=make_id("greenhouse", ext),
                    source="greenhouse",
                    external_id=ext,
                    title=(item.get("title") or "").strip(),
                    company=(item.get("company_name") or board.replace("-", " ").title()).strip(),
                    location=location,
                    work_mode=detect_work_mode(location, description[:800]),
                    description=description,
                    url=item.get("absolute_url", ""),
                    posted_at=parse_date(item.get("updated_at")),
                    ats="greenhouse",
                )
            )
        return jobs

    # -- Lever --------------------------------------------------------------
    async def _lever(self, client: httpx.AsyncClient, company: str) -> list[JobPosting]:
        url = f"https://api.lever.co/v0/postings/{company}"
        resp = await client.get(
            url, params={"mode": "json"}, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        jobs = []
        for item in payload:
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            description = item.get("descriptionPlain") or strip_html(item.get("description"))
            for section in item.get("lists") or []:
                description += "\n" + section.get("text", "") + "\n" + strip_html(section.get("content"))
            ext = f"{company}:{item.get('id')}"
            jobs.append(
                JobPosting(
                    id=make_id("lever", ext),
                    source="lever",
                    external_id=ext,
                    title=(item.get("text") or "").strip(),
                    company=company.replace("-", " ").title(),
                    location=location,
                    work_mode=detect_work_mode(location, item.get("workplaceType"), description[:800]),
                    employment_type=categories.get("commitment") or "",
                    description=description.strip(),
                    url=item.get("hostedUrl", ""),
                    posted_at=parse_date((item.get("createdAt") or 0) / 1000 or None),
                    tags=[t for t in [categories.get("team"), categories.get("department")] if t],
                    ats="lever",
                )
            )
        return jobs

    # -- Ashby --------------------------------------------------------------
    async def _ashby(self, client: httpx.AsyncClient, board: str) -> list[JobPosting]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
        resp = await client.get(
            url, params={"includeCompensation": "true"}, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        jobs = []
        for item in resp.json().get("jobs", []):
            description = item.get("descriptionPlain") or strip_html(item.get("descriptionHtml"))
            location = item.get("location") or ""
            ext = f"{board}:{item.get('id')}"
            comp = item.get("compensation") or {}
            salary_text = ""
            summary = comp.get("compensationTierSummary") or comp.get("summaryComponents")
            if isinstance(summary, str):
                salary_text = summary
            jobs.append(
                JobPosting(
                    id=make_id("ashby", ext),
                    source="ashby",
                    external_id=ext,
                    title=(item.get("title") or "").strip(),
                    company=board.replace("-", " ").title(),
                    location=location,
                    work_mode="remote" if item.get("isRemote") else detect_work_mode(
                        location, description[:800]
                    ),
                    employment_type=item.get("employmentType") or "",
                    description=description,
                    url=item.get("jobUrl") or item.get("applyUrl") or "",
                    salary_text=salary_text,
                    posted_at=parse_date(item.get("publishedAt")),
                    tags=[t for t in [item.get("department"), item.get("team")] if t],
                    ats="ashby",
                )
            )
        return jobs

    # -- Workable -----------------------------------------------------------
    async def _workable(self, client: httpx.AsyncClient, account: str) -> list[JobPosting]:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{account}"
        resp = await client.get(
            url, params={"details": "true"}, headers={"User-Agent": USER_AGENT}
        )
        resp.raise_for_status()
        payload = resp.json()
        jobs = []
        for item in payload.get("jobs", []):
            loc = item.get("location") or {}
            if isinstance(loc, dict):
                location = ", ".join(
                    str(v) for v in [loc.get("city"), loc.get("country")] if v
                )
            else:
                location = str(loc)
            description = strip_html(item.get("description")) or strip_html(item.get("requirements"))
            ext = f"{account}:{item.get('shortcode') or item.get('id')}"
            jobs.append(
                JobPosting(
                    id=make_id("workable", ext),
                    source="workable",
                    external_id=ext,
                    title=(item.get("title") or "").strip(),
                    company=payload.get("name") or account.replace("-", " ").title(),
                    location=location,
                    work_mode="remote" if item.get("telecommuting") else detect_work_mode(
                        location, description[:800]
                    ),
                    employment_type=item.get("employment_type") or "",
                    description=description,
                    url=item.get("url") or item.get("application_url") or "",
                    posted_at=parse_date(item.get("published_on") or item.get("created_at")),
                    ats="workable",
                )
            )
        return jobs
