"""API anahtarı gerektiren toplayıcılar: Adzuna ve Jooble.

Anahtar yoksa kaynak kendini kapatır (`enabled` False) ve pipeline sessizce
diğer kaynaklarla devam eder — MVP anahtarsız da çalışır.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..schemas import JobPosting, SearchCriteria, SearchPlan
from .base import USER_AGENT, JobSource, detect_work_mode, make_id, parse_date, strip_html

# Adzuna ülke kodları (destekledikleri pazarlar). Türkiye listede yok —
# Türkiye seçiliyse bu kaynak atlanır, Jooble devreye girer.
ADZUNA_COUNTRIES = {
    "austria": "at", "avusturya": "at",
    "australia": "au", "avustralya": "au",
    "belgium": "be", "belçika": "be",
    "brazil": "br", "brezilya": "br",
    "canada": "ca", "kanada": "ca",
    "switzerland": "ch", "isviçre": "ch", "i̇sviçre": "ch",
    "germany": "de", "almanya": "de", "deutschland": "de",
    "spain": "es", "ispanya": "es",
    "france": "fr", "fransa": "fr",
    "united kingdom": "gb", "uk": "gb", "england": "gb", "birleşik krallık": "gb", "i̇ngiltere": "gb",
    "india": "in", "hindistan": "in",
    "italy": "it", "italya": "it", "i̇talya": "it",
    "mexico": "mx", "meksika": "mx",
    "netherlands": "nl", "hollanda": "nl",
    "new zealand": "nz", "yeni zelanda": "nz",
    "poland": "pl", "polonya": "pl",
    "singapore": "sg", "singapur": "sg",
    "united states": "us", "usa": "us", "us": "us", "abd": "us", "amerika": "us",
    "south africa": "za", "güney afrika": "za",
}


def adzuna_country_code(name: str) -> str | None:
    return ADZUNA_COUNTRIES.get(name.strip().lower())


class AdzunaSource(JobSource):
    name = "adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs"

    @property
    def enabled(self) -> bool:
        return get_settings().adzuna_enabled

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        settings = get_settings()
        codes: list[str] = []
        for country in criteria.countries:
            code = adzuna_country_code(country)
            if code and code not in codes:
                codes.append(code)
        if not codes:
            codes = ["gb", "us"] if "remote" in criteria.work_modes else []
        if not codes:
            return []

        query = " ".join(plan.queries[:2]) or " ".join(plan.titles[:2])
        where = criteria.cities[0] if criteria.cities else ""
        per_country = max(10, limit // len(codes))
        out: list[JobPosting] = []

        for code in codes:
            params = {
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_app_key,
                "results_per_page": min(50, per_country),
                "what": query,
                "max_days_old": criteria.posted_within_days,
                "content-type": "application/json",
            }
            if where:
                params["where"] = where
            resp = await client.get(
                f"{self.BASE}/{code}/search/1", params=params, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            for item in resp.json().get("results", []):
                ext = str(item.get("id"))
                description = strip_html(item.get("description"))
                location = (item.get("location") or {}).get("display_name", "")
                salary_min, salary_max = item.get("salary_min"), item.get("salary_max")
                salary_text = ""
                if salary_min and salary_max:
                    salary_text = f"{int(salary_min):,} - {int(salary_max):,}"
                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=(item.get("title") or "").strip(),
                        company=((item.get("company") or {}).get("display_name") or "").strip(),
                        location=location,
                        work_mode=detect_work_mode(location, item.get("title"), description[:800]),
                        employment_type=item.get("contract_time") or item.get("contract_type") or "",
                        description=description,
                        url=item.get("redirect_url", ""),
                        salary_text=salary_text,
                        posted_at=parse_date(item.get("created")),
                    )
                )
            if len(out) >= limit:
                break
        return out[:limit]


class JoobleSource(JobSource):
    """Jooble toplayıcısı.

    ÖNEMLİ — anahtarlar bölgeseldir. jooble.org üzerinden alınan anahtar ABD
    indeksini sorgular ve Türkiye şehirlerine boş döner; aynı anahtar
    tr.jooble.org'da 403 alır (ölçüldü). Türkiye ilanları için anahtarı
    tr.jooble.org/api/about üzerinden alıp `JOOBLE_HOST` ayarını o adrese
    çevirmek gerekir.
    """

    name = "jooble"

    @property
    def enabled(self) -> bool:
        return get_settings().jooble_enabled

    async def fetch(self, client, plan, criteria, limit) -> list[JobPosting]:
        settings = get_settings()
        # Boş string = lokasyon filtresi yok. "remote" bir lokasyon DEĞİL;
        # onu location olarak göndermek Jooble'da hep sıfır sonuç veriyordu.
        locations = criteria.cities or criteria.countries or [""]

        keywords = ", ".join(plan.queries[:3]) or ", ".join(plan.titles[:3])
        out: list[JobPosting] = []
        seen: set[str] = set()

        for location in locations[:3]:
            payload = {"keywords": keywords, "page": "1"}
            if location:
                payload["location"] = location
            resp = await client.post(
                f"{settings.jooble_host.rstrip('/')}/api/{settings.jooble_api_key}",
                json=payload,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                ext = str(item.get("id") or item.get("link"))
                if ext in seen:
                    continue
                seen.add(ext)
                description = strip_html(item.get("snippet"))
                job_location = item.get("location") or ""
                out.append(
                    JobPosting(
                        id=make_id(self.name, ext),
                        source=self.name,
                        external_id=ext,
                        title=(item.get("title") or "").strip(),
                        company=(item.get("company") or "").strip(),
                        location=job_location,
                        work_mode=detect_work_mode(job_location, item.get("title"), description),
                        employment_type=item.get("type") or "",
                        description=description,
                        url=item.get("link", ""),
                        salary_text=item.get("salary") or "",
                        posted_at=parse_date(item.get("updated")),
                    )
                )
                if len(out) >= limit:
                    return out
        return out
