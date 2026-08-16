"use client";

import { useState } from "react";
import ApplicationKitPanel from "./ApplicationKitPanel";
import { createApplicationKit } from "@/lib/api";
import type { ApplicationKitResponse, JobMatch, Verdict, WorkMode } from "@/lib/types";

const VERDICT_LABEL: Record<Verdict, string> = {
  strong: "Güçlü eşleşme",
  good: "İyi aday",
  stretch: "Zorlayıcı",
  poor: "Uyumsuz",
};

const WORK_MODE_LABEL: Record<WorkMode, string> = {
  remote: "Uzaktan",
  hybrid: "Hibrit",
  onsite: "Ofisten",
  unknown: "Belirtilmemiş",
};

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days <= 0) return "bugün";
  if (days === 1) return "dün";
  if (days < 30) return `${days} gün önce`;
  return date.toLocaleDateString("tr-TR");
}

export default function MatchCard({
  match,
  profileId,
}: {
  match: JobMatch;
  profileId: string;
}) {
  const [open, setOpen] = useState(false);
  const [kit, setKit] = useState<ApplicationKitResponse | null>(null);
  const [building, setBuilding] = useState(false);
  const [kitError, setKitError] = useState<string | null>(null);

  async function handleBuildKit() {
    setBuilding(true);
    setKitError(null);
    try {
      setKit(await createApplicationKit(profileId, match.job.id));
    } catch (err) {
      setKitError(err instanceof Error ? err.message : "Başvuru kiti üretilemedi.");
    } finally {
      setBuilding(false);
    }
  }
  const { job } = match;
  const posted = formatDate(job.posted_at);

  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`verdict-${match.verdict} rounded-full px-2.5 py-1 text-xs font-semibold`}
            >
              {VERDICT_LABEL[match.verdict]}
            </span>
            {job.ats && (
              <span
                className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700"
                title="İşverenin kendi başvuru sistemi — otomatik başvuruya uygun"
              >
                {job.ats}
              </span>
            )}
            {match.scored_by === "rules" && (
              <span
                className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-800"
                title="Bu ilan yalnızca kural bazlı skorlandı"
              >
                kural skoru
              </span>
            )}
          </div>

          <h3 className="mt-2 text-base font-semibold text-gray-900">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-blue-700 hover:underline"
            >
              {job.title}
            </a>
          </h3>

          <p className="mt-0.5 text-sm text-gray-700">{job.company}</p>

          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
            <span>{WORK_MODE_LABEL[job.work_mode]}</span>
            {job.location && <span>· {job.location}</span>}
            {job.employment_type && <span>· {job.employment_type}</span>}
            {job.salary_text && <span>· {job.salary_text}</span>}
            {posted && <span>· {posted}</span>}
            <span>· {job.source}</span>
          </div>
        </div>

        <ScoreDial score={match.score} />
      </div>

      {match.reasons.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm text-gray-700">
          {match.reasons.slice(0, open ? undefined : 2).map((reason, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      )}

      {match.matched_skills.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {match.matched_skills.slice(0, 8).map((skill) => (
            <span
              key={skill}
              className="rounded-md bg-green-50 px-2 py-0.5 text-xs text-green-800 ring-1 ring-green-200"
            >
              {skill}
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="mt-4 space-y-3 border-t border-gray-200 pt-4 text-sm">
          {match.missing_skills.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                Eksik görünenler
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {match.missing_skills.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-md bg-red-50 px-2 py-0.5 text-xs text-red-800 ring-1 ring-red-200"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {match.risks.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                Dikkat edilmesi gerekenler
              </p>
              <ul className="mt-1.5 list-disc pl-5 text-gray-700">
                {match.risks.map((risk, i) => (
                  <li key={i}>{risk}</li>
                ))}
              </ul>
            </div>
          )}

          {job.description && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                İlan metni (kısaltılmış)
              </p>
              <p className="mt-1.5 whitespace-pre-line text-gray-700">
                {job.description.slice(0, 1200)}
                {job.description.length > 1200 ? "…" : ""}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg bg-gray-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-gray-800"
        >
          İlana git
        </a>
        {!kit && (
          <button
            onClick={handleBuildKit}
            disabled={building}
            className="rounded-lg bg-violet-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-gray-400"
          >
            {building ? "CV hazırlanıyor…" : "İlana özel CV hazırla"}
          </button>
        )}
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-sm font-medium text-blue-600 hover:text-blue-700"
        >
          {open ? "Daralt" : "Detay"}
        </button>
      </div>

      {building && (
        <p className="mt-3 rounded-lg bg-violet-50 px-3 py-2 text-xs text-violet-900">
          Bu ilana özel CV, ön yazı ve vurgulanacak maddeler üretiliyor — 40-90 saniye sürebilir.
        </p>
      )}
      {kitError && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{kitError}</p>
      )}
      {kit && <ApplicationKitPanel data={kit} />}
    </article>
  );
}

function ScoreDial({ score }: { score: number }) {
  const color =
    score >= 85 ? "text-green-600" : score >= 65 ? "text-blue-600" : score >= 40 ? "text-amber-600" : "text-gray-400";
  return (
    <div className="shrink-0 text-right">
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{score}</div>
      <div className="text-[10px] uppercase tracking-wide text-gray-400">uygunluk</div>
    </div>
  );
}
