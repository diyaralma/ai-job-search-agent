"use client";

import { useState } from "react";
import {
  clearJoobleSettings,
  saveJoobleSettings,
  type JoobleSettings,
} from "@/lib/api";

/**
 * Jooble keys are regional: a key issued on jooble.org queries the US index and
 * returns nothing for Turkish cities, while the same key gets a 403 on
 * tr.jooble.org. So the host is picked alongside the key, and the "get a key"
 * link follows the selected region.
 */
const HOSTS = [
  { value: "https://tr.jooble.org", label: "Turkey", note: "tr.jooble.org" },
  { value: "https://jooble.org", label: "Global", note: "jooble.org" },
];

export default function JoobleKeyCard({
  settings,
  onChange,
}: {
  settings: JoobleSettings;
  onChange: (next: JoobleSettings) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [apiKey, setApiKey] = useState("");
  // Not configured yet: default to Turkey. That is what this card is for, and
  // .env.example ships the global host, which would otherwise preselect Global.
  const [host, setHost] = useState(
    settings.configured ? settings.host : HOSTS[0].value,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      onChange(await saveJoobleSettings(apiKey.trim(), host));
      setApiKey("");
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the key.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClear() {
    setBusy(true);
    setError(null);
    try {
      onChange(await clearJoobleSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the key.");
    } finally {
      setBusy(false);
    }
  }

  // Configured and not being edited: stay out of the way.
  if (settings.configured && !editing) {
    return (
      <div className="mb-6 flex flex-wrap items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-900">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-600" aria-hidden />
        <span>
          Jooble connected —{" "}
          <span className="font-medium">{hostLabel(settings.host)}</span> listings
          are included in searches.
        </span>
        <span className="ml-auto flex gap-3">
          <button
            onClick={() => setEditing(true)}
            className="font-medium text-green-800 underline hover:text-green-900"
          >
            Change key
          </button>
          <button
            onClick={handleClear}
            disabled={busy}
            className="text-green-700 underline hover:text-green-900 disabled:opacity-50"
          >
            Remove
          </button>
        </span>
      </div>
    );
  }

  const selected = HOSTS.find((h) => h.value === host) ?? HOSTS[0];

  return (
    <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3.5 text-sm text-blue-900">
      <p className="font-medium">Searching in Turkey? Add a free Jooble key.</p>
      <p className="mt-1 text-blue-800">
        None of the key-free sources carry Turkish job listings. Jooble does, and its
        API is free — but the key is <strong>yours</strong>, and it is tied to the
        region you get it from.
      </p>

      <ol className="mt-3 list-decimal space-y-1 pl-5 text-blue-800">
        <li>Pick your region below.</li>
        <li>
          Get a key from{" "}
          <a
            href={`${selected.value}/api/about`}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium underline hover:text-blue-950"
          >
            {selected.note}/api/about
          </a>{" "}
          — it arrives by email, no card needed.
        </li>
        <li>Paste it here. It is stored locally in <code className="rounded bg-blue-100 px-1">agent/.env</code>, never sent anywhere else.</li>
      </ol>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1.5">
          {HOSTS.map((h) => (
            <button
              key={h.value}
              type="button"
              onClick={() => setHost(h.value)}
              aria-pressed={host === h.value}
              className={[
                "rounded-full px-3 py-1.5 text-xs transition",
                host === h.value
                  ? "bg-blue-600 text-white"
                  : "bg-white text-blue-900 ring-1 ring-blue-200 hover:bg-blue-100",
              ].join(" ")}
            >
              {h.label}
            </button>
          ))}
        </div>

        <input
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && apiKey.trim() && !busy) void handleSave();
          }}
          placeholder="Paste your Jooble API key"
          autoComplete="off"
          spellCheck={false}
          className="min-w-[16rem] flex-1 rounded-lg border border-blue-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />

        <button
          onClick={handleSave}
          disabled={busy || !apiKey.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-400"
        >
          {busy ? "Saving…" : "Save"}
        </button>

        {settings.configured && (
          <button
            onClick={() => {
              setEditing(false);
              setApiKey("");
            }}
            className="text-sm text-blue-800 underline hover:text-blue-950"
          >
            Cancel
          </button>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </div>
  );
}

function hostLabel(host: string): string {
  return HOSTS.find((h) => h.value === host)?.note ?? host;
}
