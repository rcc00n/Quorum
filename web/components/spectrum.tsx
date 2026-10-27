"use client";
import { useState } from "react";
import { SpectrumField } from "./spectrum-field";
import { Source, rating, cohort, safeUrl } from "@/lib/api";
export function Spectrum({ sources, standalone = false }: { sources: Source[]; standalone?: boolean }) {
  const Heading = standalone ? "h1" : "h2";
  const [mode, setMode] = useState("average");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <section className={`spectrum spectrum-modern${standalone ? " spectrum-standalone" : ""}`}>
      <div className="section-heading">
        <Heading>Source spectrum</Heading>
        <label className="inline-label">
          Rating mode
          <select
            aria-label="Rating mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="allsides">AllSides</option>
            <option value="mbfc">MBFC</option>
            <option value="adfontes">Ad Fontes</option>
            <option value="average">Average</option>
          </select>
        </label>
      </div>
      <p className="help">
        External source ratings describe editorial position, not factual
        accuracy. Average = mean of available normalized ratings. Missing
        ratings are excluded, never treated as zero.
      </p>
      <SpectrumField sources={sources} mode={mode} selectedId={selectedId} onSelect={setSelectedId} />
      <div className="spectrum-axis">
        <span>Left −1</span>
        <span>Center 0</span>
        <span>Right +1</span>
      </div>
      {sources.length ? (
        sources.map((s) => {
          const score = rating(s, mode);
          return (
            <div className="source-row" key={s.id}>
              <button type="button" className="sp-source-button" aria-pressed={selectedId === s.id} onClick={() => setSelectedId(s.id)}>
                {s.name}
                {s.audience !== null && s.audience_source_url && (
                  <small className="audience-value">
                    Audience: {s.audience.toLocaleString()}
                  </small>
                )}
              </button>
              {score === null ? (
                <span className="source-score">Unrated</span>
              ) : (
                <>
                  <div className="spectrum-track">
                    <span style={{ left: `${(score + 1) * 50}%` }} />
                  </div>
                  <span className="source-score">
                    {cohort(score)} · {score.toFixed(2)}
                  </span>
                </>
              )}
                {s.rating_provenance && <details className="rating-provenance">
                  <summary title="Inspect provider labels, source URLs and registry dates">Rating provenance: {s.name}</summary>
                  <p>Registry checked: {s.ratings_checked_at || "Not supplied"}</p>
                  {(["allsides", "mbfc", "adfontes"] as const).map(provider => <p key={provider}>
                    {provider === "allsides" ? "AllSides" : provider === "mbfc" ? "MBFC" : "Ad Fontes"}: {s[provider] === null ? "Unrated" : s[provider]}
                    {s.rating_labels?.[provider] ? ` · ${s.rating_labels[provider]}` : ""}{" "}
                    {s.rating_provenance?.[provider] && safeUrl(s.rating_provenance[provider]!) && <a href={safeUrl(s.rating_provenance[provider]!)} target="_blank" rel="noopener noreferrer">Provider source</a>}
                  </p>)}
                  {s.audience_source_url && safeUrl(s.audience_source_url) && <p><a href={safeUrl(s.audience_source_url)} target="_blank" rel="noopener noreferrer">Audience source</a> · Reporting date: {s.audience_as_of || "Not supplied"}</p>}
                </details>}
            </div>
          );
        })
      ) : (
        <p className="muted">
          No rated sources are available for this selection.
        </p>
      )}
      <details>
        <summary>How ratings are calculated</summary>
        <p>
          AllSides: −1, −0.5, 0, +0.5, +1. MBFC: −1, −0.67, −0.33, 0, +0.33,
          +0.67, +1. Ad Fontes: bias ÷ 42. Collector values are already
          normalized. Left ≤ −0.25; right ≥ +0.25; center lies between. Audience
          is only displayed when supplied; no audience or cohort shares are
          estimated.
        </p>
      </details>
    </section>
  );
}
