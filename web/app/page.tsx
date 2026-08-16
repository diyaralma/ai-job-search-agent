"use client";

import { useEffect, useState } from "react";
import CriteriaForm from "@/components/CriteriaForm";
import CvUploader from "@/components/CvUploader";
import MatchList from "@/components/MatchList";
import ProfileCard from "@/components/ProfileCard";
import { getHealth, runSearch, type Health } from "@/lib/api";
import {
  DEFAULT_CRITERIA,
  type ProfileResponse,
  type SearchCriteria,
  type SearchResponse,
} from "@/lib/types";

const PROFILE_STORAGE_KEY = "job-agent:profile";

export default function Home() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [criteria, setCriteria] = useState<SearchCriteria>(DEFAULT_CRITERIA);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [llm, setLlm] = useState<Health["llm"] | null>(null);

  // Keep the profile so a page refresh does not force re-uploading the CV
  useEffect(() => {
    const stored = localStorage.getItem(PROFILE_STORAGE_KEY);
    if (stored) {
      try {
        setProfile(JSON.parse(stored) as ProfileResponse);
      } catch {
        localStorage.removeItem(PROFILE_STORAGE_KEY);
      }
    }
  }, []);

  // Is the service up and is the selected model provider ready — warn before the
  // user starts a search. The agent produces the warning text: what is missing
  // depends on which provider is selected (CLI, API key, model name…).
  useEffect(() => {
    getHealth()
      .then((health) => {
        setLlm(health.llm);
        if (!health.llm.ready) {
          setWarning(`CV analysis and matching will not work. ${health.llm.detail}`);
        }
      })
      .catch((err: unknown) => {
        setWarning(err instanceof Error ? err.message : "Could not reach the agent service.");
      });
  }, []);

  function handleParsed(next: ProfileResponse) {
    setProfile(next);
    setResult(null);
    setError(null);
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(next));
  }

  function handleReset() {
    setProfile(null);
    setResult(null);
    setError(null);
    localStorage.removeItem(PROFILE_STORAGE_KEY);
  }

  async function handleSearch() {
    if (!profile) return;
    setSearching(true);
    setError(null);
    try {
      setResult(await runSearch(profile.profile_id, criteria));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:py-14">
      <header className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
          AI Job Search Agent
        </h1>
        <p className="mt-2 text-gray-600">
          Upload your CV and set your criteria. The agent scans open job sources and
          employers&apos; own application boards, then ranks the results by how well they fit you.
        </p>
        {llm && (
          <p className="mt-3 flex items-center gap-2 text-xs text-gray-500">
            <span
              className={[
                "inline-block h-1.5 w-1.5 rounded-full",
                llm.ready ? "bg-green-500" : "bg-amber-500",
              ].join(" ")}
              aria-hidden
            />
            <span>
              Model: <span className="font-medium text-gray-700">{llm.provider}</span> ·{" "}
              {llm.model}
            </span>
            <span className="text-gray-400">— change it in agent/.env</span>
          </p>
        )}
      </header>

      {warning && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {warning}
        </div>
      )}

      <div className="space-y-6">
        <section>
          <StepLabel n={1} title="Upload CV" done={!!profile} />
          {profile ? (
            <ProfileCard data={profile} onReset={handleReset} />
          ) : (
            <CvUploader onParsed={handleParsed} />
          )}
        </section>

        {profile && (
          <section>
            <StepLabel n={2} title="Set criteria" done={!!result} />
            <CriteriaForm
              criteria={criteria}
              onChange={setCriteria}
              onSubmit={handleSearch}
              busy={searching}
            />
          </section>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        {searching && (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
            <p className="text-sm font-medium text-gray-800">
              Scanning postings and evaluating them for you…
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Collecting from the sources plus AI scoring usually takes 30-90 seconds.
            </p>
          </div>
        )}

        {result && profile && !searching && (
          <section>
            <StepLabel n={3} title="Results" done />
            <MatchList result={result} profileId={profile.profile_id} />
          </section>
        )}
      </div>

      <footer className="mt-14 border-t border-gray-200 pt-6 text-xs text-gray-500">
        <p>
          Postings are collected from open APIs (Remotive, Jobicy, Himalayas, RemoteOK,
          Arbeitnow, Adzuna, Jooble) and from employers&apos; own ATS boards (Greenhouse,
          Lever, Ashby, Workable). Tailored CVs are built only from facts in your profile —
          missing skills are never invented, they are listed separately. Applications always
          go through the job owner&apos;s own system.
        </p>
      </footer>
    </main>
  );
}

function StepLabel({ n, title, done }: { n: number; title: string; done?: boolean }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span
        className={[
          "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold",
          done ? "bg-green-600 text-white" : "bg-gray-900 text-white",
        ].join(" ")}
      >
        {done ? "✓" : n}
      </span>
      <h2 className="text-sm font-medium uppercase tracking-wide text-gray-600">{title}</h2>
    </div>
  );
}
