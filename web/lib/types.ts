// Agent servisindeki Pydantic şemalarının TypeScript karşılığı.
// agent/app/schemas.py değiştiğinde burası da güncellenmeli.

export type Seniority =
  | "intern"
  | "junior"
  | "mid"
  | "senior"
  | "lead"
  | "principal"
  | "executive";

export type WorkMode = "remote" | "hybrid" | "onsite" | "unknown";
export type Verdict = "strong" | "good" | "stretch" | "poor";

export interface Experience {
  title: string;
  company: string;
  start: string;
  end: string;
  highlights: string[];
}

export interface CandidateProfile {
  full_name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  years_experience: number;
  seniority: Seniority;
  target_titles: string[];
  skills: string[];
  soft_skills: string[];
  languages: string[];
  industries: string[];
  education: string[];
  certifications: string[];
  experience: Experience[];
  summary: string;
}

export interface ProfileResponse {
  profile_id: string;
  profile: CandidateProfile;
  source_filename: string;
  created_at: string;
}

export interface SearchCriteria {
  countries: string[];
  cities: string[];
  work_modes: WorkMode[];
  employment_types: string[];
  seniority: Seniority[];
  min_salary: number | null;
  salary_currency: string;
  extra_keywords: string[];
  exclude_keywords: string[];
  exclude_companies: string[];
  posted_within_days: number;
  max_results: number;
}

export interface SearchPlan {
  queries: string[];
  titles: string[];
  must_have_skills: string[];
  nice_to_have_skills: string[];
  exclude_terms: string[];
  locations: string[];
  rationale: string;
}

export interface JobPosting {
  id: string;
  source: string;
  external_id: string;
  title: string;
  company: string;
  location: string;
  work_mode: WorkMode;
  employment_type: string;
  description: string;
  url: string;
  salary_text: string;
  posted_at: string | null;
  tags: string[];
  ats: string;
}

export interface JobMatch {
  job: JobPosting;
  score: number;
  verdict: Verdict;
  matched_skills: string[];
  missing_skills: string[];
  reasons: string[];
  risks: string[];
  prefilter_score: number;
  scored_by: "llm" | "rules";
}

export interface SearchStats {
  fetched: number;
  after_dedupe: number;
  after_prefilter: number;
  llm_scored: number;
  sources_used: string[];
  source_errors: Record<string, string>;
  duration_ms: number;
  /** Kriterlere uyan ilan kalmadığı için filtreler gevşetildi. */
  relaxed: boolean;
}

export interface SearchResponse {
  search_id: string;
  plan: SearchPlan;
  stats: SearchStats;
  matches: JobMatch[];
}

export const DEFAULT_CRITERIA: SearchCriteria = {
  countries: [],
  cities: [],
  work_modes: ["remote", "hybrid", "onsite"],
  employment_types: [],
  seniority: [],
  min_salary: null,
  salary_currency: "USD",
  extra_keywords: [],
  exclude_keywords: [],
  exclude_companies: [],
  posted_within_days: 45,
  max_results: 30,
};

// --- Başvuru kiti ---------------------------------------------------------

export interface TailoredExperience {
  title: string;
  company: string;
  period: string;
  bullets: string[];
}

export interface TailoredCV {
  full_name: string;
  headline: string;
  contact: string;
  summary: string;
  skills: string[];
  experience: TailoredExperience[];
  education: string[];
  languages: string[];
}

export interface ApplicationKit {
  language: string;
  cv: TailoredCV;
  cover_letter: string;
  talking_points: string[];
  why_me: string;
  /** Bu ilan için öne çıkarılanlar — şeffaflık */
  emphasized: string[];
  /** Geri plana atılanlar — şeffaflık */
  downplayed: string[];
  /** Kapatılamayan eksikler; mülakatta sorulabilir */
  gaps_to_expect: string[];
}

export interface ApplicationKitResponse {
  application_id: string;
  job: JobPosting;
  kit: ApplicationKit;
  created_at: string;
}
