import type {
  ApplicationKitResponse,
  ProfileResponse,
  SearchCriteria,
  SearchResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";

/** FastAPI hata gövdesinden okunabilir mesaj çıkarır. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    }
  } catch {
    // JSON değilse aşağıdaki genel mesaja düş
  }
  return `Sunucu hatası (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new Error(
      `Agent servisine ulaşılamadı (${BASE}). Servisin çalıştığından emin olun.`,
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
  /** Seçili model sağlayıcısı — agent/.env içindeki LLM_PROVIDER ile belirlenir. */
  llm: {
    provider: string;
    model: string;
    /** Çağrı yapmadan anlaşılan hazırlık durumu (CLI var mı, anahtar tanımlı mı…). */
    ready: boolean;
    /** Hazır değilse ne yapılacağını anlatan mesaj; doğrudan kullanıcıya gösterilir. */
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

/** CV indirme bağlantısı — tarayıcı doğrudan agent servisinden indirir. */
export function cvDownloadUrl(applicationId: string, format: "pdf" | "docx"): string {
  return `${BASE}/api/applications/${applicationId}/cv.${format}`;
}
