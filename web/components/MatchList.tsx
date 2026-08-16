"use client";

import { useMemo, useState } from "react";
import MatchCard from "./MatchCard";
import type { SearchResponse, Verdict } from "@/lib/types";

const FILTERS: { value: Verdict | "all"; label: string }[] = [
  { value: "all", label: "Tümü" },
  { value: "strong", label: "Güçlü" },
  { value: "good", label: "İyi" },
  { value: "stretch", label: "Zorlayıcı" },
  { value: "poor", label: "Uyumsuz" },
];

export default function MatchList({
  result,
  profileId,
}: {
  result: SearchResponse;
  profileId: string;
}) {
  const [filter, setFilter] = useState<Verdict | "all">("all");

  const counts = useMemo(() => {
    const acc: Record<string, number> = { all: result.matches.length };
    for (const m of result.matches) acc[m.verdict] = (acc[m.verdict] ?? 0) + 1;
    return acc;
  }, [result.matches]);

  const visible = useMemo(
    () => (filter === "all" ? result.matches : result.matches.filter((m) => m.verdict === filter)),
    [result.matches, filter],
  );

  const errorEntries = Object.entries(result.stats.source_errors);

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold text-gray-900">
            {result.matches.length} eşleşme
          </h2>
          <span className="text-xs text-gray-500">
            {(result.stats.duration_ms / 1000).toFixed(1)} sn ·{" "}
            {result.stats.sources_used.join(", ") || "kaynak yok"}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
          <Stat label="Çekilen ilan" value={result.stats.fetched} />
          <Stat label="Tekilleştirme sonrası" value={result.stats.after_dedupe} />
          <Stat label="Ön elemeyi geçen" value={result.stats.after_prefilter} />
          <Stat label="Yapay zekâ skorlaması" value={result.stats.llm_scored} />
        </div>

        {!result.stats.relaxed && result.stats.after_prefilter < 15 && (
          <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-sm text-blue-900">
            <span className="font-medium">Kriterlerinize uyan ilan havuzu dar</span> —
            filtreyi yalnızca {result.stats.after_prefilter} ilan geçti. Ücretsiz
            kaynakların hiçbiri Türkiye ilanlarını kapsamıyor; kapsamı genişletmek için{" "}
            <a
              href="https://jooble.org/api/about"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-blue-700"
            >
              ücretsiz Jooble anahtarı
            </a>{" "}
            alıp <code className="rounded bg-blue-100 px-1">agent/.env</code> içine ekleyin.
          </div>
        )}

        {result.stats.relaxed && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
            <span className="font-medium">Kriterlerinize uyan ilan bulunamadı.</span>{" "}
            Ekran boş kalmasın diye lokasyon filtresi gevşetildi — aşağıdaki ilanlar
            seçtiğiniz ülke/şehir dışında olabilir. Kapsamı artırmak için{" "}
            <code className="rounded bg-amber-100 px-1">JOOBLE_API_KEY</code> tanımlayın
            (Türkiye ilanları için) ya da uzaktan çalışmayı seçili bırakın.
          </div>
        )}

        {result.plan.rationale && (
          <p className="mt-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-900">
            <span className="font-medium">Arama stratejisi: </span>
            {result.plan.rationale}
          </p>
        )}

        {result.plan.queries.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-gray-500">Kullanılan sorgular:</span>
            {result.plan.queries.map((q) => (
              <span key={q} className="rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                {q}
              </span>
            ))}
          </div>
        )}

        {errorEntries.length > 0 && (
          <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <span className="font-medium">Ulaşılamayan kaynaklar: </span>
            {errorEntries.map(([name, err]) => `${name} (${err})`).join(", ")}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={[
              "rounded-full px-3 py-1.5 text-sm transition",
              filter === f.value
                ? "bg-gray-900 text-white"
                : "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50",
            ].join(" ")}
          >
            {f.label}
            <span className="ml-1.5 text-xs opacity-70">{counts[f.value] ?? 0}</span>
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-600">
          Bu filtrede sonuç yok.
        </p>
      ) : (
        <div className="space-y-3">
          {visible.map((match) => (
            <MatchCard key={match.job.id} match={match} profileId={profileId} />
          ))}
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-gray-50 px-3 py-2.5">
      <div className="text-xl font-semibold tabular-nums text-gray-900">{value}</div>
      <div className="text-[11px] leading-tight text-gray-500">{label}</div>
    </div>
  );
}
