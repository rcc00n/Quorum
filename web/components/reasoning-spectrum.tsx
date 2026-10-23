"use client";
import { useState } from "react";
import type { ReasoningStory } from "@/lib/reasoning";
import type { Source } from "@/lib/api";
import { Sources } from "./reasoning-evidence";
import { Spectrum } from "./spectrum";
const names = {
  average: "Average",
  allsides: "AllSides",
  mbfc: "MBFC",
  adfontes: "Ad Fontes",
};
export function ReasoningSpectrum({
  story,
  sources,
}: {
  story: ReasoningStory;
  sources: Source[];
}) {
  const [mode, setMode] = useState<keyof typeof names>(
    story.spectrum.rating_mode,
  );
  const sp = story.spectrum;
  return (
    <section id="reasoning-perspectives" className="r-section">
      <p className="eyebrow">ACROSS THE SPECTRUM</p>
      <h2>Perspective Comparison</h2>
      <div className="section-heading">
        <p>Source coverage, not independent confirmation or audience reach.</p>
        <label className="inline-label">
          Cohort rating context
          <select
            aria-label="Cohort rating context"
            value={mode}
            onChange={(e) => setMode(e.target.value as keyof typeof names)}
          >
            {Object.entries(names).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="r-unavailable" role="status">
        Individual source ratings and audience estimates are not supplied.{" "}
        {mode !== sp.rating_mode
          ? `${names[mode]} cohorts cannot be recalculated. `
          : ""}
        Counts below remain the recorded {names[sp.rating_mode]} cohorts.
      </p>
      <div className="r-cohort-head" aria-hidden="true">
        <span>Left</span>
        <span>Right</span>
      </div>
      <div className="r-cohorts">
        {(
          ["major_left", "major_right", "minor_left", "minor_right"] as const
        ).map((key) => {
          const pair = sp.coverage[key],
            outlets = sp.outlets?.filter((o) => o.cohort === key) || [];
          return (
            <article className="r-cohort" key={key}>
              <h3>{key.replace("_", " ")}</h3>
              <p className="r-cohort-number">
                {pair ? (
                  <>
                    <strong>{pair[0]}</strong> / {pair[1]}
                    <small>covered / eligible sources</small>
                  </>
                ) : (
                  "Coverage unavailable"
                )}
              </p>
              {pair && (
                <div className="r-coverage-bar" aria-hidden="true">
                  <span
                    style={{
                      width: (pair[1] ? (100 * pair[0]) / pair[1] : 0) + "%",
                    }}
                  />
                </div>
              )}
              {pair?.[1] === 0 && (
                <p className="help">
                  No eligible sources in this recorded cohort.
                </p>
              )}
              {outlets.length > 0 && (
                <p className="r-cohort-names">
                  {outlets.map((o) => o.source).join(" · ")}
                </p>
              )}
              {outlets.length ? (
                <details className="r-cohort-details">
                  <summary>
                    Inspect {outlets.length} supplied{" "}
                    {outlets.length === 1 ? "outlet" : "outlets"}
                    <span className="r-disclosure-icon" aria-hidden="true">
                      +
                    </span>
                  </summary>
                  <div>
                    {outlets.map((o, i) => (
                      <div className="r-outlet" key={i}>
                        <Sources sources={[{ title: o.source, url: o.url }]} />
                        <p>{o.highlights || "No emphasis supplied."}</p>
                        {o.interpretation_label && (
                          <small>
                            Interpretation: {o.interpretation_label}
                          </small>
                        )}
                        {o.omits && <p>Omissions reported: {o.omits}</p>}
                        {o.wording && <small>Wording: “{o.wording}”</small>}
                      </div>
                    ))}
                  </div>
                </details>
              ) : (
                <p className="help">
                  No covered outlet names supplied for this cohort.
                </p>
              )}
            </article>
          );
        })}
      </div>
      {sp.coverage.center && (
        <p className="help">
          Center, outside the four cohorts: {sp.coverage.center[0]} covered /{" "}
          {sp.coverage.center[1]} eligible.
        </p>
      )}
      <p className="help">
        Only structurally supplied cohort membership is shown. The full eligible
        registry is not enumerated.
      </p>
      <div className="r-interpretations">
        {sp.interpretations.map((i, index) => (
          <p key={index}>
            “{i.label}” · {i.outlets} outlets · mostly {i.mostly}
          </p>
        ))}
      </div>
      {(["left", "right"] as const).map((side) => (
        <details key={side}>
          <summary>{side} — supplied framing summary</summary>
          <p>{sp[side].highlights || "Highlights unavailable."}</p>
          <p>{sp[side].omits || "Omissions not supplied."}</p>
          <p>{sp[side].wording}</p>
          {sp[side].example_url && (
            <Sources
              sources={[
                { title: "Original example", url: sp[side].example_url },
              ]}
            />
          )}
        </details>
      ))}
      {sp.note && <p>{sp.note}</p>}
      <Spectrum sources={sources} />
    </section>
  );
}
