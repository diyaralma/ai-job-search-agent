"""Tüm pipeline boyunca dolaşan veri tipleri.

CandidateProfile, SearchPlan ve ScoredBatch doğrudan Claude'un structured
output şeması olarak kullanılıyor — bu yüzden alan açıklamaları modelin
gördüğü talimatın bir parçası. Değiştirirken bunu göz önünde tut.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "executive"]
WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
Verdict = Literal["strong", "good", "stretch", "poor"]


# --------------------------------------------------------------------------
# CV
# --------------------------------------------------------------------------
class Experience(BaseModel):
    title: str = Field(description="Pozisyon adı")
    company: str = Field(description="Şirket adı; bilinmiyorsa 'Bilinmiyor'")
    start: str = Field(description="Başlangıç, YYYY-MM ya da YYYY; bilinmiyorsa boş string")
    end: str = Field(description="Bitiş, YYYY-MM / YYYY / 'present'; bilinmiyorsa boş string")
    highlights: list[str] = Field(description="En fazla 4 maddede somut çıktı/başarı")


class CandidateProfile(BaseModel):
    """CV'den çıkarılan yapılandırılmış aday profili."""

    full_name: str = Field(description="Adayın tam adı; CV'de yoksa boş string")
    headline: str = Field(description="Tek cümlelik profesyonel özet, ör. 'Backend developer, 5 yıl Python'")
    email: str = Field(description="E-posta; yoksa boş string")
    phone: str = Field(description="Telefon; yoksa boş string")
    location: str = Field(description="Adayın mevcut şehir/ülkesi; yoksa boş string")
    years_experience: float = Field(description="Toplam profesyonel deneyim yılı; tahmin et, bilinmiyorsa 0")
    seniority: Seniority = Field(description="Deneyim ve sorumluluklara göre seviye")
    target_titles: list[str] = Field(
        description="Bu adayın gerçekçi olarak başvurabileceği 3-8 pozisyon adı, İngilizce"
    )
    skills: list[str] = Field(description="Teknik yetkinlikler ve teknolojiler, tekil ve normalize")
    soft_skills: list[str] = Field(description="Aktarılabilir/soft beceriler, en fazla 8")
    languages: list[str] = Field(description="Konuşulan diller ve seviyeleri, ör. 'İngilizce (C1)'")
    industries: list[str] = Field(description="Deneyim sahibi olduğu sektörler")
    education: list[str] = Field(description="Eğitim satırları, ör. 'BSc Bilgisayar Müh. - ODTÜ (2019)'")
    certifications: list[str] = Field(description="Sertifikalar; yoksa boş liste")
    experience: list[Experience] = Field(description="İş deneyimleri, en yeniden eskiye")
    summary: str = Field(description="Adayın 3-5 cümlelik değerlendirme özeti, Türkçe")


# --------------------------------------------------------------------------
# Kullanıcı kriterleri + arama planı
# --------------------------------------------------------------------------
class SearchCriteria(BaseModel):
    countries: list[str] = Field(default_factory=list, description="Ülke adları, ör. ['Türkiye', 'Germany']")
    cities: list[str] = Field(default_factory=list, description="Şehirler, ör. ['İstanbul', 'Berlin']")
    work_modes: list[WorkMode] = Field(default_factory=lambda: ["remote", "hybrid", "onsite"])
    employment_types: list[str] = Field(default_factory=list, description="full_time, part_time, contract, internship")
    seniority: list[Seniority] = Field(default_factory=list)
    min_salary: float | None = None
    salary_currency: str = "USD"
    extra_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    posted_within_days: int = 45
    max_results: int = 40


class SearchPlan(BaseModel):
    """Profil + kriterlerden türetilen, kaynaklara gönderilecek arama planı."""

    queries: list[str] = Field(
        description="İş sitelerine gönderilecek 3-6 arama sorgusu, İngilizce, kısa ve genel tut"
    )
    titles: list[str] = Field(description="Hedeflenen pozisyon adları, İngilizce")
    must_have_skills: list[str] = Field(description="İlanda aranması beklenen çekirdek yetkinlikler")
    nice_to_have_skills: list[str] = Field(description="Artı değer sayılacak yetkinlikler")
    exclude_terms: list[str] = Field(description="İlan başlığında görülürse eleme yapılacak terimler")
    locations: list[str] = Field(description="Kaynaklara gönderilecek lokasyon filtreleri; remote ise 'remote' ekle")
    rationale: str = Field(description="Bu planı neden seçtiğinin 2-3 cümlelik Türkçe açıklaması")


# --------------------------------------------------------------------------
# İlan
# --------------------------------------------------------------------------
class JobPosting(BaseModel):
    id: str
    source: str
    external_id: str
    title: str
    company: str
    location: str = ""
    work_mode: WorkMode = "unknown"
    employment_type: str = ""
    description: str = ""
    url: str
    salary_text: str = ""
    posted_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    # ATS panolarında başvuru formu doğrudan doldurulabilir; premium akışı buna bakar
    ats: str = ""

    def digest(self, max_chars: int = 2400) -> str:
        """LLM'e gönderilecek kompakt gösterim."""
        desc = " ".join(self.description.split())
        if len(desc) > max_chars:
            desc = desc[:max_chars] + "…"
        parts = [
            f"id: {self.id}",
            f"title: {self.title}",
            f"company: {self.company}",
            f"location: {self.location or 'belirtilmemiş'}",
            f"work_mode: {self.work_mode}",
        ]
        if self.employment_type:
            parts.append(f"employment_type: {self.employment_type}")
        if self.salary_text:
            parts.append(f"salary: {self.salary_text}")
        if self.posted_at:
            parts.append(f"posted_at: {self.posted_at.date().isoformat()}")
        parts.append(f"description: {desc}")
        return "\n".join(parts)


# --------------------------------------------------------------------------
# Eşleştirme
# --------------------------------------------------------------------------
class JobScore(BaseModel):
    job_id: str = Field(description="Skorlanan ilanın id'si, sana verilen değerle birebir aynı olmalı")
    score: int = Field(description="0-100 arası uygunluk skoru")
    verdict: Verdict = Field(
        description="strong=hemen başvur, good=iyi aday, stretch=zorlayıcı ama denenebilir, poor=uyumsuz"
    )
    matched_skills: list[str] = Field(description="İlanın aradığı ve adayda olan yetkinlikler")
    missing_skills: list[str] = Field(description="İlanın aradığı ama adayda görünmeyen yetkinlikler")
    reasons: list[str] = Field(description="Skoru gerekçelendiren 2-4 madde, Türkçe")
    risks: list[str] = Field(description="Başvuru öncesi dikkat edilmesi gerekenler, Türkçe; yoksa boş liste")


class ScoredBatch(BaseModel):
    scores: list[JobScore] = Field(description="Sana verilen HER ilan için tam olarak bir skor nesnesi")


class JobMatch(BaseModel):
    """API'nin döndürdüğü birleşik sonuç."""

    job: JobPosting
    score: int
    verdict: Verdict
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    prefilter_score: float = 0.0
    scored_by: Literal["llm", "rules"] = "rules"


# --------------------------------------------------------------------------
# API sözleşmesi
# --------------------------------------------------------------------------
class SearchRequest(BaseModel):
    profile_id: str
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)


class SearchStats(BaseModel):
    fetched: int = 0
    after_dedupe: int = 0
    after_prefilter: int = 0
    llm_scored: int = 0
    sources_used: list[str] = Field(default_factory=list)
    source_errors: dict[str, str] = Field(default_factory=dict)
    duration_ms: int = 0
    #: Kriterlere uyan hiç ilan kalmadığı için filtreler gevşetildi.
    #: Arayüz bunu göstermeli — yoksa kullanıcı Türkiye seçtiği halde neden
    #: Berlin ilanı gördüğünü anlamıyor.
    relaxed: bool = False


class SearchResponse(BaseModel):
    search_id: str
    plan: SearchPlan
    stats: SearchStats
    matches: list[JobMatch]


class ProfileResponse(BaseModel):
    profile_id: str
    profile: CandidateProfile
    source_filename: str
    created_at: datetime


# --------------------------------------------------------------------------
# Başvuru kiti (ilana özel CV + ön yazı)
# --------------------------------------------------------------------------
class TailoredExperience(BaseModel):
    title: str = Field(description="Pozisyon adı, CV'dekiyle aynı — değiştirme")
    company: str = Field(description="Şirket adı, CV'dekiyle aynı — değiştirme")
    period: str = Field(description="Dönem, ör. '2022-03 – present'")
    bullets: list[str] = Field(
        description="Bu ilana göre yeniden yazılmış 2-4 madde. Sadece CV'deki "
        "gerçekleri kullan; ilanın önemsediği yönleri öne çıkar."
    )


class TailoredCV(BaseModel):
    """İlana göre yeniden çerçevelenmiş CV. Yeni bilgi İÇERMEZ."""

    full_name: str = Field(description="Adayın adı, profildekiyle aynı")
    headline: str = Field(description="Bu ilana yönelik tek satırlık başlık")
    contact: str = Field(description="E-posta · telefon · konum; profilde olmayanı yazma")
    summary: str = Field(description="Bu ilana yönelik 2-4 cümlelik özet")
    skills: list[str] = Field(
        description="Profildeki yetkinlikler, ilanla ilgili olanlar önce. Yeni yetkinlik ekleme."
    )
    experience: list[TailoredExperience] = Field(description="Deneyimler, en yeniden eskiye")
    education: list[str] = Field(description="Eğitim satırları, profildekiyle aynı")
    languages: list[str] = Field(description="Diller, profildekiyle aynı")


class ApplicationKit(BaseModel):
    language: str = Field(description="Kitin dili: ilanın dili ('tr' ya da 'en')")
    cv: TailoredCV
    cover_letter: str = Field(
        description="4-6 paragraflık ön yazı, ilanın dilinde. Somut ve kısa; klişe açılış yok."
    )
    talking_points: list[str] = Field(
        description="Mülakatta/başvuruda vurgulanacak 3-5 madde, ilanın gereksinimlerine bağlı"
    )
    why_me: str = Field(
        description="'Neden bu pozisyon için uygunsunuz?' sorusuna 3-5 cümlelik cevap, ilanın dilinde"
    )
    emphasized: list[str] = Field(
        description="Bu ilan için ÖNE ÇIKARILAN profil öğeleri — şeffaflık amaçlı"
    )
    downplayed: list[str] = Field(
        description="Kısaltılan/geri plana atılan öğeler — şeffaflık amaçlı"
    )
    gaps_to_expect: list[str] = Field(
        description="İlanın istediği ama adayda olmayan şeyler; mülakatta sorulabilir. Uydurma ile kapatma."
    )


class ApplicationKitRequest(BaseModel):
    profile_id: str
    job_id: str


class ApplicationKitResponse(BaseModel):
    application_id: str
    job: JobPosting
    kit: ApplicationKit
    created_at: datetime
