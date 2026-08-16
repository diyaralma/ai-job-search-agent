"use client";

import { useRef, useState } from "react";
import { uploadCv } from "@/lib/api";
import type { ProfileResponse } from "@/lib/types";

const ACCEPT = ".pdf,.docx,.txt,.md";

export default function CvUploader({
  onParsed,
  disabled,
}: {
  onParsed: (profile: ProfileResponse) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setBusy(true);
    setFilename(file.name);
    try {
      onParsed(await uploadCv(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload the CV.");
      setFilename(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy && !disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (busy || disabled) return;
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        onClick={() => !busy && !disabled && inputRef.current?.click()}
        className={[
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
          dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white hover:border-gray-400",
          busy || disabled ? "cursor-not-allowed opacity-60" : "",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
        {busy ? (
          <>
            <Spinner />
            <p className="mt-3 text-sm font-medium text-gray-700">
              Analyzing the CV…
            </p>
            <p className="mt-1 text-xs text-gray-500">
              {filename} — this can take 15-30 seconds
            </p>
          </>
        ) : (
          <>
            <svg
              className="h-8 w-8 text-gray-400"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-.41-8.98 4.5 4.5 0 0 1 8.08-3.19 4.5 4.5 0 0 1 6.32 4.42 4.5 4.5 0 0 1-1.24 8.75H6.75Z"
              />
            </svg>
            <p className="mt-3 text-sm font-medium text-gray-800">
              Drag your CV here, or click to choose a file
            </p>
            <p className="mt-1 text-xs text-gray-500">PDF, DOCX or TXT — 25 MB max</p>
          </>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-7 w-7 animate-spin text-blue-600" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
    </svg>
  );
}
