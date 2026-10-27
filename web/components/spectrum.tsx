"use client";
import { useState } from "react";
import { SpectrumField } from "./spectrum-field";
import { Source, rating, cohort, safeUrl } from "@/lib/api";
import { cohortShares } from "@/lib/spectrum-cohorts";
const MODE_LABEL: Record<string, string> = { allsides: "AllSides", mbfc: "MBFC", adfontes: "Ad Fontes", average: "the averaged rating" };
const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)} %`);
const compact = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
// DECISION(2026-10-27, Anastasia/Claude Code; WEB-SPECTRUM-POLISH-02, Vadim's scope): the ledger of every source
// sits behind a native disclosure, "All N sources", closed by default for every viewer, under reduced motion too:
// a <details> is a plain control with no animation, the summary carries the count, the inspector above already
// shows the selected source's values, and the footnote says the unplotted sources wait below. Inside, sources
// without an editorial rating by registry metadata (`kind` official or military) form their own group at the end,
// derived from `kind`, never from a typed list; the other rows keep the registry's order. Why: Anastasia's review
// (Issue #2, 2026-10-27): forty open rows made the Sources page six screens long on a phone.
const institutional = (s: Source) => s.kind === "official" || s.kind === "military";
export function Spectrum({ sources, standalone = false }: { sources: Source[]; standalone?: boolean }) {
  const Heading = standalone ? "h1" : "h2";
  const [mode, setMode] = useState("average");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const outlets = sources.filter(s => !institutional(s));
  const bodies = sources.filter(institutional);
  const shares = cohortShares(sources.map(s => ({ id: s.id, tier: s.tier ?? null, score: rating(s, mode), audience: s.audience, audienceCited: !!safeUrl(s.audience_source_url || "") })));
  const row = (s: Source) => {
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
  };
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
      {shares.tiered > 0 && (
        <section className="sp-cohorts" aria-labelledby="sp-cohorts-head" data-mode={mode}>
          <h3 id="sp-cohorts-head">{`Registry cohorts under ${MODE_LABEL[mode] ?? mode}`}</h3>
          <table>
            <thead>
              <tr><th scope="col">Cohort</th><th scope="col">Outlets</th><th scope="col">Share of outlets</th><th scope="col">Cited audience</th><th scope="col">Share of audience</th></tr>
            </thead>
            <tbody>
              {shares.rows.map(r => (
                <tr key={r.key} data-cohort={r.key}>
                  <th scope="row">{`${r.tier === "major" ? "Major" : "Minor"} ${r.lean}`}</th>
                  <td data-outlets={r.outlets}>{r.outlets}</td>
                  <td>{pct(r.outletShare)}</td>
                  <td>{r.audience > 0 || r.withoutAudience < r.outlets ? compact(r.audience) : "—"}{r.withoutAudience > 0 ? <small>{` · ${r.withoutAudience} without a cited estimate`}</small> : null}</td>
                  <td>{pct(r.audienceShare)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="sp-cohorts-note">
            {`Shares of the ${shares.tiered} major- and minor-tier sources rated under this mode${shares.centre ? ` (${shares.centre} of them in the centre, in no cohort)` : ""}; audience shares of the ${shares.withAudience} with a cited estimate${shares.withoutAudience ? `, ${shares.withoutAudience} without one left out, not counted as zero` : ""}. Not in any cohort: ${shares.noTier} rated ${shares.noTier === 1 ? "source" : "sources"} without a tier, ${shares.unrated} unrated under this mode. Registry shares, not which sources covered an event.`}
          </p>
        </section>
      )}
      {sources.length ? (
        <details className="sp-ledger" open={ledgerOpen} onToggle={(e) => setLedgerOpen(e.currentTarget.open)}>
          <summary>{`All ${sources.length} sources`}</summary>
          <div className="spectrum-axis">
            <span>Left −1</span>
            <span>Center 0</span>
            <span>Right +1</span>
          </div>
          {outlets.map(row)}
          {bodies.length > 0 && (
            <div className="sp-ledger-group" role="group" aria-labelledby="sp-ledger-bodies">
              <h3 id="sp-ledger-bodies" className="sp-ledger-group-head">
                {`${bodies.length} official and institutional ${bodies.length === 1 ? "source" : "sources"} · no editorial rating`}
              </h3>
              {bodies.map(row)}
            </div>
          )}
        </details>
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
