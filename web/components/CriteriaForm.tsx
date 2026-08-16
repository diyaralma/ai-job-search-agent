"use client";

import { useState } from "react";
import type { SearchCriteria, Seniority, WorkMode } from "@/lib/types";

const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "remote", label: "Uzaktan" },
  { value: "hybrid", label: "Hibrit" },
  { value: "onsite", label: "Ofisten" },
];

const SENIORITIES: { value: Seniority; label: string }[] = [
  { value: "intern", label: "Stajyer" },
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Orta" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
  { value: "principal", label: "Principal" },
  { value: "executive", label: "Yönetici" },
];

/** "İstanbul, Berlin" -> ["İstanbul", "Berlin"] */
function splitList(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

export default function CriteriaForm({
  criteria,
  onChange,
  onSubmit,
  busy,
}: {
  criteria: SearchCriteria;
  onChange: (next: SearchCriteria) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  // Metin alanlarını ayrı tutuyoruz: kullanıcı "Berlin," yazarken her tuşta
  // diziye çevirmek imleci ve virgülü bozuyor.
  const [countries, setCountries] = useState(criteria.countries.join(", "));
  const [cities, setCities] = useState(criteria.cities.join(", "));
  const [excludeKeywords, setExcludeKeywords] = useState(criteria.exclude_keywords.join(", "));
  const [excludeCompanies, setExcludeCompanies] = useState(criteria.exclude_companies.join(", "));

  function set<K extends keyof SearchCriteria>(key: K, value: SearchCriteria[K]) {
    onChange({ ...criteria, [key]: value });
  }

  function toggle<T>(list: T[], value: T): T[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <h2 className="text-lg font-semibold text-gray-900">Arama kriterleri</h2>
      <p className="mt-1 text-sm text-gray-600">
        Boş bıraktığınız alanlar filtre uygulanmadığı anlamına gelir.
      </p>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <Field label="Ülkeler" hint="Virgülle ayırın">
          <input
            className={inputClass}
            placeholder="Türkiye, Germany, Netherlands"
            value={countries}
            onChange={(e) => {
              setCountries(e.target.value);
              set("countries", splitList(e.target.value));
            }}
          />
        </Field>

        <Field label="Şehirler" hint="Virgülle ayırın">
          <input
            className={inputClass}
            placeholder="İstanbul, Berlin"
            value={cities}
            onChange={(e) => {
              setCities(e.target.value);
              set("cities", splitList(e.target.value));
            }}
          />
        </Field>

        <Field label="Çalışma şekli">
          <div className="flex flex-wrap gap-2">
            {WORK_MODES.map((mode) => (
              <Toggle
                key={mode.value}
                active={criteria.work_modes.includes(mode.value)}
                onClick={() => set("work_modes", toggle(criteria.work_modes, mode.value))}
              >
                {mode.label}
              </Toggle>
            ))}
          </div>
        </Field>

        <Field label="Seviye" hint="Seçilmezse tüm seviyeler">
          <div className="flex flex-wrap gap-2">
            {SENIORITIES.map((s) => (
              <Toggle
                key={s.value}
                active={criteria.seniority.includes(s.value)}
                onClick={() => set("seniority", toggle(criteria.seniority, s.value))}
              >
                {s.label}
              </Toggle>
            ))}
          </div>
        </Field>

        <Field label="Hariç tutulacak kelimeler" hint="İlan başlığında geçerse elenir">
          <input
            className={inputClass}
            placeholder="sales, unpaid, commission"
            value={excludeKeywords}
            onChange={(e) => {
              setExcludeKeywords(e.target.value);
              set("exclude_keywords", splitList(e.target.value));
            }}
          />
        </Field>

        <Field label="Hariç tutulacak şirketler">
          <input
            className={inputClass}
            placeholder="Eski İşverenim A.Ş."
            value={excludeCompanies}
            onChange={(e) => {
              setExcludeCompanies(e.target.value);
              set("exclude_companies", splitList(e.target.value));
            }}
          />
        </Field>

        <Field label="İlan yaşı (gün)">
          <input
            type="number"
            min={1}
            max={365}
            className={inputClass}
            value={criteria.posted_within_days}
            onChange={(e) => set("posted_within_days", Number(e.target.value) || 45)}
          />
        </Field>

        <Field label="Sonuç sayısı">
          <input
            type="number"
            min={5}
            max={100}
            className={inputClass}
            value={criteria.max_results}
            onChange={(e) => set("max_results", Number(e.target.value) || 30)}
          />
        </Field>
      </div>

      <button
        onClick={onSubmit}
        disabled={busy}
        className="mt-6 w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-400 sm:w-auto sm:px-8"
      >
        {busy ? "İlanlar taranıyor…" : "İlanları tara ve eşleştir"}
      </button>
    </section>
  );
}

const inputClass =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-800">{label}</label>
      {hint && <p className="mb-1.5 text-xs text-gray-500">{hint}</p>}
      <div className={hint ? "" : "mt-1.5"}>{children}</div>
    </div>
  );
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "rounded-full px-3 py-1.5 text-sm transition",
        active
          ? "bg-blue-600 text-white"
          : "bg-gray-100 text-gray-700 hover:bg-gray-200",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
