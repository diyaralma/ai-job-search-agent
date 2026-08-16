"use client";

import { useState } from "react";
import type { ProfileResponse } from "@/lib/types";

const SENIORITY_LABEL: Record<string, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
  lead: "Lead",
  principal: "Principal",
  executive: "Executive",
};

export default function ProfileCard({
  data,
  onReset,
}: {
  data: ProfileResponse;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const p = data.profile;

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900">
            {p.full_name || "Unnamed candidate"}
          </h2>
          <p className="mt-0.5 text-sm text-gray-600">{p.headline}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-600">
            <Chip>{SENIORITY_LABEL[p.seniority] ?? p.seniority}</Chip>
            <Chip>{p.years_experience} yrs experience</Chip>
            {p.location && <Chip>{p.location}</Chip>}
            <Chip>{data.source_filename}</Chip>
          </div>
        </div>
        <button
          onClick={onReset}
          className="shrink-0 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          Upload a different CV
        </button>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-gray-700">{p.summary}</p>

      <div className="mt-4">
        <SkillRow label="Skills" items={p.skills} limit={14} />
        <SkillRow label="Target roles" items={p.target_titles} limit={8} />
      </div>

      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-4 text-sm font-medium text-blue-600 hover:text-blue-700"
      >
        {open ? "Hide details" : "Show full profile details"}
      </button>

      {open && (
        <div className="mt-4 space-y-4 border-t border-gray-200 pt-4 text-sm">
          {p.experience.length > 0 && (
            <div>
              <h3 className="font-medium text-gray-900">Experience</h3>
              <ul className="mt-2 space-y-3">
                {p.experience.map((exp, i) => (
                  <li key={i}>
                    <p className="font-medium text-gray-800">
                      {exp.title} — {exp.company}
                    </p>
                    <p className="text-xs text-gray-500">
                      {[exp.start, exp.end].filter(Boolean).join(" → ") || "No dates given"}
                    </p>
                    {exp.highlights.length > 0 && (
                      <ul className="mt-1 list-disc pl-5 text-gray-700">
                        {exp.highlights.map((h, j) => (
                          <li key={j}>{h}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <SkillRow label="Languages" items={p.languages} limit={10} />
          <SkillRow label="Industries" items={p.industries} limit={10} />
          <SkillRow label="Education" items={p.education} limit={10} />
          <SkillRow label="Certifications" items={p.certifications} limit={10} />
        </div>
      )}
    </section>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">{children}</span>
  );
}

function SkillRow({ label, items, limit }: { label: string; items: string[]; limit: number }) {
  if (!items?.length) return null;
  const shown = items.slice(0, limit);
  const rest = items.length - shown.length;
  return (
    <div className="mt-3 first:mt-0">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {shown.map((item) => (
          <span
            key={item}
            className="rounded-md bg-gray-50 px-2 py-1 text-xs text-gray-700 ring-1 ring-gray-200"
          >
            {item}
          </span>
        ))}
        {rest > 0 && <span className="px-1 py-1 text-xs text-gray-500">+{rest}</span>}
      </div>
    </div>
  );
}
