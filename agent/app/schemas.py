"""The data types that flow through the whole pipeline.

CandidateProfile, SearchPlan, ScoredBatch and ApplicationKit are used directly as
the model's structured-output schema — which means the field descriptions are
part of the instruction the model sees. Keep that in mind when editing them.
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
    title: str = Field(description="Job title")
    company: str = Field(description="Company name; 'Unknown' if not stated")
    start: str = Field(description="Start, YYYY-MM or YYYY; empty string if unknown")
    end: str = Field(description="End, YYYY-MM / YYYY / 'present'; empty string if unknown")
    highlights: list[str] = Field(description="Up to 4 bullets with concrete outcomes")


class CandidateProfile(BaseModel):
    """Structured candidate profile extracted from the CV."""

    full_name: str = Field(description="Candidate's full name; empty string if absent")
    headline: str = Field(description="One-line professional summary, e.g. 'Backend developer, 5 years of Python'")
    email: str = Field(description="Email; empty string if absent")
    phone: str = Field(description="Phone; empty string if absent")
    location: str = Field(description="Candidate's current city/country; empty string if absent")
    years_experience: float = Field(description="Total years of professional experience; estimate, 0 if unknown")
    seniority: Seniority = Field(description="Level, based on experience and responsibilities")
    target_titles: list[str] = Field(
        description="3-8 job titles this candidate could realistically apply for, in English"
    )
    skills: list[str] = Field(description="Technical skills and technologies, deduplicated and normalized")
    soft_skills: list[str] = Field(description="Transferable / soft skills, at most 8")
    languages: list[str] = Field(description="Spoken languages with levels, e.g. 'English (C1)'")
    industries: list[str] = Field(description="Industries the candidate has worked in")
    education: list[str] = Field(description="Education entries, e.g. 'BSc Computer Engineering - METU (2019)'")
    certifications: list[str] = Field(description="Certifications; empty list if none")
    experience: list[Experience] = Field(description="Work experience, newest first")
    summary: str = Field(description="3-5 sentence assessment of the candidate, in English")


# --------------------------------------------------------------------------
# User criteria + search plan
# --------------------------------------------------------------------------
class SearchCriteria(BaseModel):
    countries: list[str] = Field(default_factory=list, description="Country names, e.g. ['Turkey', 'Germany']")
    cities: list[str] = Field(default_factory=list, description="Cities, e.g. ['Istanbul', 'Berlin']")
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
    """Search plan derived from the profile + criteria, sent to the sources."""

    queries: list[str] = Field(
        description="3-6 search queries to send to job boards, in English, short and general"
    )
    titles: list[str] = Field(description="Target job titles, in English")
    must_have_skills: list[str] = Field(description="Core skills expected to appear in the posting")
    nice_to_have_skills: list[str] = Field(description="Skills that count as a plus")
    exclude_terms: list[str] = Field(description="Terms that disqualify a posting if seen in its title")
    locations: list[str] = Field(description="Location filters for the sources; add 'remote' if remote is wanted")
    rationale: str = Field(description="2-3 sentences in English explaining why you chose this plan")


# --------------------------------------------------------------------------
# Job posting
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
    # On ATS boards the application form can be filled directly; the premium
    # flow builds on this.
    ats: str = ""

    def digest(self, max_chars: int = 2400) -> str:
        """Compact representation sent to the LLM."""
        desc = " ".join(self.description.split())
        if len(desc) > max_chars:
            desc = desc[:max_chars] + "…"
        parts = [
            f"id: {self.id}",
            f"title: {self.title}",
            f"company: {self.company}",
            f"location: {self.location or 'not specified'}",
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
# Matching
# --------------------------------------------------------------------------
class JobScore(BaseModel):
    job_id: str = Field(description="Id of the scored posting, copied verbatim from the input")
    score: int = Field(description="Fit score between 0 and 100")
    verdict: Verdict = Field(
        description="strong=apply now, good=solid candidate, stretch=hard but worth a try, poor=mismatch"
    )
    matched_skills: list[str] = Field(description="Skills the posting asks for and the candidate has")
    missing_skills: list[str] = Field(description="Skills the posting asks for but the candidate lacks")
    reasons: list[str] = Field(description="2-4 bullets justifying the score, in English")
    risks: list[str] = Field(description="Things to check before applying, in English; empty list if none")


class ScoredBatch(BaseModel):
    scores: list[JobScore] = Field(description="Exactly one score object for EVERY posting you were given")


class JobMatch(BaseModel):
    """The combined result returned by the API."""

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
# API contract
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
    #: Filters were relaxed because nothing matched the criteria. The UI must
    #: show this — otherwise the user cannot tell why they picked Turkey and
    #: got a Berlin posting.
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
# Application kit (job-specific CV + cover letter)
# --------------------------------------------------------------------------
class TailoredExperience(BaseModel):
    title: str = Field(description="Job title, same as in the CV — do not change it")
    company: str = Field(description="Company name, same as in the CV — do not change it")
    period: str = Field(description="Period, e.g. '2022-03 – present'")
    bullets: list[str] = Field(
        description="2-4 bullets rewritten for this posting. Use only facts from the "
        "CV; foreground what the posting cares about."
    )


class TailoredCV(BaseModel):
    """CV reframed for a specific posting. Contains NO new information."""

    full_name: str = Field(description="Candidate's name, same as in the profile")
    headline: str = Field(description="One-line headline aimed at this posting")
    contact: str = Field(description="Email · phone · location; never invent what the profile lacks")
    summary: str = Field(description="2-4 sentence summary aimed at this posting")
    skills: list[str] = Field(
        description="Skills from the profile, the posting-relevant ones first. Do not add new skills."
    )
    experience: list[TailoredExperience] = Field(description="Experience, newest first")
    education: list[str] = Field(description="Education entries, same as in the profile")
    languages: list[str] = Field(description="Languages, same as in the profile")


class ApplicationKit(BaseModel):
    language: str = Field(description="Language of the kit: the posting's language ('tr' or 'en')")
    cv: TailoredCV
    cover_letter: str = Field(
        description="4-6 paragraph cover letter in the posting's language. Concrete and short; no cliché opener."
    )
    talking_points: list[str] = Field(
        description="3-5 points to emphasize in the application/interview, tied to the posting's requirements"
    )
    why_me: str = Field(
        description="3-5 sentence answer to 'why are you a fit for this role?', in the posting's language"
    )
    emphasized: list[str] = Field(
        description="Profile items FOREGROUNDED for this posting — for transparency"
    )
    downplayed: list[str] = Field(
        description="Items shortened or pushed to the background — for transparency"
    )
    gaps_to_expect: list[str] = Field(
        description="What the posting wants but the candidate lacks; may come up in the interview. Never paper over it."
    )


class ApplicationKitRequest(BaseModel):
    profile_id: str
    job_id: str


# --------------------------------------------------------------------------
# Optional source credentials the UI can set
# --------------------------------------------------------------------------
class JoobleSettingsRequest(BaseModel):
    """The key is write-only: it is stored in agent/.env and never sent back."""

    api_key: str = Field(description="Jooble API key, from <host>/api/about")
    host: str = Field(
        default="https://tr.jooble.org",
        description="The regional host the key was issued for",
    )


class JoobleSettings(BaseModel):
    configured: bool
    host: str


class ApplicationKitResponse(BaseModel):
    application_id: str
    job: JobPosting
    kit: ApplicationKit
    created_at: datetime
