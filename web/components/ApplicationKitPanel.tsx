"use client";

import { useState } from "react";
import { cvDownloadUrl } from "@/lib/api";
import type { ApplicationKitResponse } from "@/lib/types";

/** Copy to clipboard, with feedback. */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
      className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 transition hover:bg-gray-50"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

function Block({
  title,
  children,
  copyText,
}: {
  title: string;
  children: React.ReactNode;
  copyText?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h4>
        {copyText && <CopyButton text={copyText} label="Copy" />}
      </div>
      {children}
    </div>
  );
}

export default function ApplicationKitPanel({ data }: { data: ApplicationKitResponse }) {
  const { kit, job, application_id } = data;

  return (
    <div className="mt-4 space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Application kit ready</h3>
          <p className="text-xs text-gray-600">
            {job.company} · {job.title} · language: {kit.language === "tr" ? "Turkish" : "English"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={cvDownloadUrl(application_id, "pdf")}
            className="rounded-lg bg-gray-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            Download CV (PDF)
          </a>
          <a
            href={cvDownloadUrl(application_id, "docx")}
            className="rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50"
          >
            DOCX
          </a>
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-violet-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-violet-700"
          >
            Open posting and apply
          </a>
        </div>
      </div>

      <Block title="Cover letter" copyText={kit.cover_letter}>
        <p className="whitespace-pre-line text-sm leading-relaxed text-gray-800">
          {kit.cover_letter}
        </p>
      </Block>

      <Block title="Why me?" copyText={kit.why_me}>
        <p className="whitespace-pre-line text-sm leading-relaxed text-gray-800">{kit.why_me}</p>
      </Block>

      {kit.talking_points.length > 0 && (
        <Block title="Talking points" copyText={kit.talking_points.join("\n")}>
          <ul className="list-disc space-y-1 pl-5 text-sm text-gray-800">
            {kit.talking_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </Block>
      )}

      {/* Transparency: the user must know what they are signing */}
      <div className="grid gap-3 sm:grid-cols-2">
        {kit.emphasized.length > 0 && (
          <Block title="Foregrounded for this posting">
            <ul className="space-y-1 text-sm text-gray-700">
              {kit.emphasized.map((item, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-green-600">↑</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Block>
        )}
        {kit.downplayed.length > 0 && (
          <Block title="Pushed to the background">
            <ul className="space-y-1 text-sm text-gray-700">
              {kit.downplayed.map((item, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-gray-400">↓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Block>
        )}
      </div>

      {kit.gaps_to_expect.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-amber-900">
            May come up in the interview — not added to the CV
          </h4>
          <p className="mb-2 text-xs text-amber-800">
            Things the posting asks for that are not in your profile. Deliberately not fabricated — go in prepared.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
            {kit.gaps_to_expect.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      <details className="rounded-lg border border-gray-200 bg-white p-4">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-gray-500">
          View the tailored CV content
        </summary>
        <div className="mt-3 space-y-3 text-sm text-gray-800">
          <div>
            <p className="font-semibold">{kit.cv.full_name}</p>
            <p className="text-gray-600">{kit.cv.headline}</p>
            <p className="text-xs text-gray-500">{kit.cv.contact}</p>
          </div>
          <p className="leading-relaxed">{kit.cv.summary}</p>
          <p className="text-xs text-gray-600">{kit.cv.skills.join(" · ")}</p>
          {kit.cv.experience.map((exp, i) => (
            <div key={i}>
              <p className="font-medium">
                {exp.title} — {exp.company}
              </p>
              <p className="text-xs text-gray-500">{exp.period}</p>
              <ul className="mt-1 list-disc pl-5">
                {exp.bullets.map((b, j) => (
                  <li key={j}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
