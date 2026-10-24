"use client";
import { useState } from "react";
import { Source, rating, cohort, safeUrl } from "@/lib/api";
export function Spectrum({ sources }: { sources: Source[] }) {
  const [mode, setMode] = useState("average");
  const points = sources.flatMap((source) => {
    const score = rating(source, mode);
    return score !== null &&
      source.audience !== null &&
      source.audience > 0 &&
      !!source.audience_source_url
      ? [{ source, score, log: Math.log10(source.audience) }]
      : [];
  });
  const low = Math.min(...points.map((p) => p.log));
  const high = Math.max(...points.map((p) => p.log));
  return (
    <section className="spectrum">
      <div className="section-heading">
        <h2>Source spectrum</h2>
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
      {points.length > 0 && (
        <figure className="audience-plot">
          <figcaption>
            Source position × audience{" "}
            <span>Logarithmic audience scale · supplied estimates only</span>
          </figcaption>
          <svg
            viewBox="0 0 640 260"
            role="img"
            aria-label="Sources by external rating and audience on a logarithmic scale. Exact values follow in the source list."
          >
            <line x1="45" x2="615" y1="220" y2="220" stroke="#a8b9ae" />
            <line x1="45" x2="45" y1="25" y2="220" stroke="#a8b9ae" />
            <line x1="330" x2="330" y1="25" y2="220" stroke="#e2e8e5" />
            <text x="45" y="245">
              −1
            </text>
            <text x="326" y="245">
              0
            </text>
            <text x="597" y="245">
              +1
            </text>
            {points.map((p) => (
              <circle
                key={p.source.id}
                cx={45 + (p.score + 1) * 285}
                cy={
                  high === low
                    ? 120
                    : 210 - ((p.log - low) / (high - low)) * 170
                }
                r="5"
                fill="#16766d"
              >
                <title>
                  {p.source.name}: {p.score.toFixed(2)}, audience{" "}
                  {p.source.audience?.toLocaleString()}
                </title>
              </circle>
            ))}
          </svg>
        </figure>
      )}
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
              <span>
                {s.name}
                {s.audience !== null && s.audience_source_url && (
                  <small className="audience-value">
                    Audience: {s.audience.toLocaleString()}
                  </small>
                )}
              </span>
              {score === null ? (
                <span>Unrated</span>
              ) : (
                <>
                  <div className="spectrum-track">
                    <span style={{ left: `${(score + 1) * 50}%` }} />
                  </div>
                  <span>
                    {cohort(score)} · {score.toFixed(2)}
                  </span>
                </>
              )}
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
