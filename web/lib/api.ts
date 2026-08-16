import type {
  ApplicationKitResponse,
  ProfileResponse,
  SearchCriteria,
  SearchResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";

/** Extracts a readable message from a FastAPI error body. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    }
  } catch {
    // Not JSON — fall through to the generic message below
  }
  return `Server error (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new Error(
      `Could not reach the agent service (${BASE}). Make sure it is running.`,
    );
  }
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

export async function uploadCv(file: File): Promise<ProfileResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<ProfileResponse>("/api/cv", { method: "POST", body: form });
}

export async function runSearch(
  profileId: string,
  criteria: SearchCriteria,
): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId, criteria }),
  });
}

export type Health = {
  status: string;
  /** The selected model provider — set with LLM_PROVIDER in agent/.env. */
  llm: {
    provider: string;
    model: string;
    /** Readiness determined without making a call (is the CLI there, is a key set…). */
    ready: boolean;
    /** If not ready, what to do about it; shown to the user verbatim. */
    detail: string;
  };
  sources: { name: string; enabled: boolean }[];
};

export async function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export async function createApplicationKit(
  profileId: string,
  jobId: string,
): Promise<ApplicationKitResponse> {
  return request<ApplicationKitResponse>("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId, job_id: jobId }),
  });
}

/** CV download link — the browser downloads straight from the agent service. */
export function cvDownloadUrl(applicationId: string, format: "pdf" | "docx"): string {
  return `${BASE}/api/applications/${applicationId}/cv.${format}`;
}
