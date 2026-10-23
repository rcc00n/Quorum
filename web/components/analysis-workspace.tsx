"use client";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowUpRight,
  ChevronDown,
  FileText,
  GitCompareArrows,
  History,
  SearchCheck,
} from "lucide-react";
import type { Event, Source } from "@/lib/api";
import { rating, cohort, safeUrl } from "@/lib/api";
import type {
  Citation,
  Claim,
  Document,
  Publication,
  Verification,
} from "@/lib/analysis";
import { displayTime } from "@/lib/analysis";
import { Spectrum } from "./spectrum";

const statusNames = {
  established: "Established",
  attributed: "Attributed",
  disputed: "Disputed",
  unknown: "Unknown",
};
const accessNames = {
  1: "Full text permitted",
  2: "Headline / lead only",
  3: "Coverage only",
};
const actionNames = {
  collection: "Sources collected",
  clustering: "Event grouped",
  claim_extraction: "Claims identified",
  evidence_search: "Evidence searched",
  zetaris_query: "Data queried through Zetaris",
  primary_verification: "Primary review",
  independent_verification: "Independent review",
  contradiction_detection: "Disagreement identified",
  recheck: "Additional review",
  conclusion_revision: "Conclusion revised",
  publication: "Result published",
};
function Unavailable({ children }: { children: React.ReactNode }) {
  return <p className="analysis-unavailable">{children}</p>;
}
function SourceLink({
  url,
  children,
}: {
  url: string;
  children: React.ReactNode;
}) {
  const safe = safeUrl(url);
  return safe ? (
    <a
      className="source-link"
      href={safe}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <ArrowUpRight size={14} />
    </a>
  ) : (
    <span>Source link unavailable</span>
  );
}
export function PublicationNotice({
  publication: p,
}: {
  publication?: Publication;
}) {
  if (!p) return null;
  if (p.status === "pending")
    return (
      <div className="publication-line">
        <span className="status-dot" />
        Analysis publication pending · catalog definitions remain available.
      </div>
    );
  const warning =
    p.status === "stale" ||
    p.status === "partial" ||
    p.status === "error" ||
    p.fallback;
  return (
    <aside
      className={warning ? "publication-notice" : "publication-line"}
      role={warning ? "status" : undefined}
    >
      <strong>
        {p.status === "error"
          ? "Analysis unavailable"
          : p.status === "stale"
            ? "This edition is out of date"
            : p.status === "partial"
              ? "This edition is incomplete"
              : "Published edition"}
      </strong>
      {p.fallback && (
        <span>
          {" "}
          · Showing the last intact revision after a publication integrity
          issue.
        </span>
      )}
      <span>
        Generated {displayTime(p.generated_at)} · Revision{" "}
        {p.revision || "unavailable"}
      </span>
      {p.expires_at && (
        <span>
          Freshness deadline {displayTime(p.expires_at)}. Publication status
          does not certify a provider or claim.
        </span>
      )}
    </aside>
  );
}
function Review({ name, value }: { name: string; value: Verification }) {
  return (
    <div className="verification">
      <p className="eyebrow">{name}</p>
      <strong>{value.status.replaceAll("_", " ")}</strong>
      <p>{value.summary || "No review findings supplied."}</p>
      <small>
        {value.actor || "Reviewer not supplied"} ·{" "}
        {displayTime(value.checked_at)}
      </small>
    </div>
  );
}
function EvidenceList({
  label,
  items,
  documents,
}: {
  label: string;
  items: Citation[];
  documents: Document[];
}) {
  return (
    <section className="citation-group">
      <h4>
        {label} <span>{items.length}</span>
      </h4>
      {items.length ? (
        items.map((citation, i) => {
          const doc = documents.find((d) => d.id === citation.document_id);
          return doc ? (
            <article className="citation" key={i}>
              <div className="citation-heading">
                <FileText size={16} />
                <strong>{doc.title}</strong>
                <span>
                  {doc.primary ? "Primary document" : "Secondary reporting"}
                </span>
              </div>
              <p>{citation.summary}</p>
              {citation.quote && <blockquote>{citation.quote}</blockquote>}
              <div className="citation-meta">
                <span>Published {displayTime(doc.published_at)}</span>
                <span>{accessNames[doc.access_level]}</span>
              </div>
              <SourceLink url={doc.url}>Read original source</SourceLink>
              <details className="document-version">
                <summary>Document provenance</summary>
                <dl>
                  <dt>Document</dt>
                  <dd>{doc.id}</dd>
                  <dt>Source</dt>
                  <dd>{doc.source_id}</dd>
                  <dt>Hash</dt>
                  <dd>{doc.content_hash}</dd>
                  <dt>Revision</dt>
                  <dd>{doc.revision || "Not supplied"}</dd>
                  <dt>Fetched</dt>
                  <dd>{displayTime(doc.fetched_at)}</dd>
                  {citation.char_start !== null && (
                    <>
                      <dt>Quote hash</dt>
                      <dd>{citation.content_hash_at_quote || "Unavailable"}</dd>
                      <dt>Quote offsets</dt>
                      <dd>
                        {citation.char_start}–{citation.char_end}
                      </dd>
                    </>
                  )}
                </dl>
              </details>
            </article>
          ) : (
            <Unavailable key={i}>Evidence metadata unavailable.</Unavailable>
          );
        })
      ) : (
        <Unavailable>
          No {label.toLowerCase()} supplied. Missing evidence does not prove a
          claim false.
        </Unavailable>
      )}
    </section>
  );
}
function ClaimDetail({
  claim,
  documents,
  index,
}: {
  claim: Claim;
  documents: Document[];
  index: number;
}) {
  return (
    <details
      className="claim-detail"
      id={"claim-" + claim.id}
      open={index === 0}
    >
      <summary>
        <span className="claim-index">
          {String(index + 1).padStart(2, "0")}
        </span>
        <div>
          <span className={"claim-state state-" + claim.status}>
            {statusNames[claim.status]}
          </span>
          <h3>{claim.text}</h3>
          {claim.attribution && (
            <p>
              {claim.attribution.speaker} ·{" "}
              {displayTime(claim.attribution.statement_at)}
            </p>
          )}
        </div>
        <ChevronDown size={18} className="disclosure-chevron" />
      </summary>
      <div className="claim-body">
        <p className="claim-explanation">{claim.explanation}</p>
        {claim.disagreement === "present" && (
          <p className="uncertainty">
            The supplied reviewers disagree. This claim remains unresolved.
          </p>
        )}
        {claim.confidence_explanation && (
          <p className="uncertainty">
            Assessment limits: {claim.confidence_explanation}
          </p>
        )}
        <div className="verification-grid">
          <Review
            name="Primary verification"
            value={claim.primary_verification}
          />
          <Review
            name="Independent verification"
            value={claim.independent_verification}
          />
        </div>
        <EvidenceList
          label="Supporting evidence"
          items={claim.supporting}
          documents={documents}
        />
        <EvidenceList
          label="Contradicting evidence"
          items={claim.contradicting}
          documents={documents}
        />
        <p className="help">
          Claim ID: {claim.id} · Classification and public verification
          summaries supplied with this analysis.
        </p>
      </div>
    </details>
  );
}
function Comparison({ event, sources }: { event: Event; sources: Source[] }) {
  const [mode, setMode] = useState("average");
  const a = event.analysis;
  if (!a)
    return (
      <Unavailable>
        Structured source comparisons have not been supplied.
      </Unavailable>
    );
  const coverage = a.coverage;
  const eligible = coverage.eligible_source_ids;
  const groups = [
    ["major", "Left"],
    ["major", "Right"],
    ["minor", "Left"],
    ["minor", "Right"],
  ];
  return (
    <>
      <div className="coverage-measures">
        <div>
          <span>Publications</span>
          <strong>{coverage.publication_count ?? "Unavailable"}</strong>
        </div>
        <div>
          <span>Independent confirmations</span>
          <strong>
            {coverage.independent_confirmation_count ?? "Unavailable"}
          </strong>
        </div>
        <div>
          <span>Audience reach</span>
          <p>See sourced estimates per outlet. No combined reach inferred.</p>
        </div>
      </div>
      <p className="help">
        Publication frequency, potential audience and independent confirmation
        measure different things. A framing example describes this publication,
        not an entire political group.
      </p>
      <div className="perspective-grid">
        {a.frames.length ? (
          a.frames.map((frame, i) => {
            const source = sources.find((s) => s.id === frame.source_id);
            const doc = a.documents.find((d) => d.id === frame.document_id);
            return (
              <article key={i} className="perspective-column">
                <p className="eyebrow">{source?.kind || "SOURCE"}</p>
                <h3>{source?.name || frame.source_id}</h3>
                <p className="help">
                  {doc
                    ? accessNames[doc.access_level]
                    : "Access level unavailable"}{" "}
                  · {displayTime(doc?.published_at)}
                </p>
                <p>{frame.summary}</p>
                <h4>Claims emphasized</h4>
                {frame.emphasized_claim_ids.length ? (
                  <ul>
                    {frame.emphasized_claim_ids.map((id) => (
                      <li key={id}>
                        <a href={"#claim-" + encodeURIComponent(id)}>
                          {a.claims.find((c) => c.id === id)?.text || id}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Unavailable>Emphasis information not supplied.</Unavailable>
                )}
                <h4>Attributed interpretations</h4>
                {frame.interpretations.length ? (
                  frame.interpretations.map((text, j) => <p key={j}>{text}</p>)
                ) : (
                  <Unavailable>No interpretation supplied.</Unavailable>
                )}
                {doc && (
                  <SourceLink url={doc.url}>Read this publication</SourceLink>
                )}
                <p className="help">
                  Independence group:{" "}
                  {source?.independence_group || "Not supplied"}
                </p>
                {source?.audience !== null &&
                source?.audience !== undefined &&
                source?.audience_source_url ? (
                  <p className="help">
                    Audience estimate: {source.audience.toLocaleString()} ·{" "}
                    {source.audience_as_of || "Date unavailable"}{" "}
                    <SourceLink url={source.audience_source_url}>
                      Estimate source
                    </SourceLink>
                  </p>
                ) : (
                  <p className="help">Sourced audience estimate unavailable.</p>
                )}
              </article>
            );
          })
        ) : (
          <Unavailable>No grounded framing differences supplied.</Unavailable>
        )}
      </div>
      <div className="cohort-section">
        <div className="section-heading">
          <h3>Coverage by source cohort</h3>
          <label className="inline-label">
            Cohort rating mode
            <select
              aria-label="Cohort rating mode"
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
        {eligible === null ? (
          <Unavailable>
            The eligible source set was not supplied. Coverage shares and
            silence cannot be inferred.
          </Unavailable>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Cohort</th>
                  <th>Covered / eligible sources</th>
                </tr>
              </thead>
              <tbody>
                {groups.map(([tier, side]) => {
                  const members = sources.filter(
                    (s) =>
                      eligible.includes(s.id) &&
                      s.tier === tier &&
                      rating(s, mode) !== null &&
                      cohort(rating(s, mode)!) === side,
                  );
                  return (
                    <tr key={tier + side}>
                      <td>
                        {tier} · {side}
                      </td>
                      <td>
                        {
                          members.filter((s) =>
                            coverage.covered_source_ids.includes(s.id),
                          ).length
                        }{" "}
                        / {members.length}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="help">
              Center, unrated and untiered sources sit outside these four
              cohorts. Counts use only the explicitly supplied eligible
              registry; no audience shares inferred.
            </p>
          </div>
        )}
      </div>
      <Spectrum sources={event.sources} />
    </>
  );
}
export function AnalysisWorkspace({
  event,
  publication,
  sources,
  supplementary = false,
}: {
  event: Event;
  publication?: Publication;
  sources: Source[];
  supplementary?: boolean;
}) {
  const a = event.analysis;
  const trace = [...(a?.trace || [])].sort(
    (x, y) =>
      x.timestamp.localeCompare(y.timestamp) || x.id.localeCompare(y.id),
  );
  return (
    <div className="analysis-workspace">
      {!supplementary && (
        <>
          <p className="eyebrow">EVENT ANALYSIS / {event.date}</p>
          <h1>{event.title}</h1>
          <p className="lede">{event.summary}</p>
          {event.importance && (
            <aside className="notice">
              <strong>{event.importance.label}</strong>
              <p>{event.importance.explanation}</p>
            </aside>
          )}
        </>
      )}
      <nav className="analysis-navigation" aria-label="Analysis sections">
        <a href="#evidence-explorer">
          <SearchCheck size={16} />
          Evidence
        </a>
        <a href="#perspective-comparison">
          <GitCompareArrows size={16} />
          Perspectives
        </a>
        <a href="#investigation-timeline">
          <History size={16} />
          Investigation
        </a>
      </nav>
      <section id="evidence-explorer" className="analysis-block">
        <div className="analysis-block-heading">
          <p className="eyebrow">01 / FOLLOW THE EVIDENCE</p>
          <h2>Evidence Explorer</h2>
          <p>
            Read the claim, inspect its sources, and see where verification
            agrees or stops.
          </p>
        </div>
        {a?.claims.length ? (
          a.claims.map((claim, i) => (
            <ClaimDetail
              key={claim.id}
              claim={claim}
              documents={a.documents}
              index={i}
            />
          ))
        ) : (
          <Unavailable>
            No structured claim/evidence records supplied. Existing brief
            sections do not imply independent verification.
          </Unavailable>
        )}
      </section>
      <section id="perspective-comparison" className="analysis-block">
        <div className="analysis-block-heading">
          <p className="eyebrow">02 / COMPARE THE COVERAGE</p>
          <h2>Perspective Comparison</h2>
          <p>
            Original publications, their emphasis and attributed
            interpretations, side by side.
          </p>
        </div>
        <Comparison event={event} sources={sources} />
      </section>
      <section id="investigation-timeline" className="analysis-block">
        <div className="analysis-block-heading">
          <p className="eyebrow">03 / SEE THE SEQUENCE</p>
          <h2>Investigation Timeline</h2>
          <p>
            Public-safe action summaries and outcomes. Private prompts and
            hidden reasoning are not displayed.
          </p>
        </div>
        {trace.length ? (
          <ol className="investigation-timeline">
            {trace.map((step) => (
              <li key={step.id}>
                <span className="timeline-dot" />
                <div className="timeline-heading">
                  <h3>{actionNames[step.action]}</h3>
                  <time dateTime={step.timestamp}>
                    {displayTime(step.timestamp)}
                  </time>
                </div>
                <p>{step.summary}</p>
                {step.outcome && (
                  <p className="timeline-outcome">{step.outcome}</p>
                )}
                <p className="help">
                  {step.actor || "Actor not supplied"}
                  {step.revision ? " · Revision " + step.revision : ""}
                </p>
                {step.evidence_refs.map((id) => {
                  const doc = a?.documents.find((d) => d.id === id);
                  return doc ? (
                    <SourceLink key={id} url={doc.url}>
                      {doc.title}
                    </SourceLink>
                  ) : null;
                })}
              </li>
            ))}
          </ol>
        ) : (
          <Unavailable>
            No investigation trace supplied. No agent steps have been inferred.
          </Unavailable>
        )}
      </section>
      <section className="revision-section">
        <h2>Revisions & corrections</h2>
        {a?.corrections.length ? (
          a.corrections.map((c, i) => (
            <article key={i}>
              <p>{c.summary}</p>
              <p className="help">
                {displayTime(c.timestamp)} · Replaces {c.supersedes_claim_id}
                {c.replacement_claim_id
                  ? " with " + c.replacement_claim_id
                  : " (withdrawn)"}
              </p>
              <Link
                className="source-link"
                href={`/events/${encodeURIComponent(event.id)}?date=${event.date}&revision=${encodeURIComponent(c.previous_revision)}`}
              >
                Read previous revision <ArrowUpRight size={14} />
              </Link>
            </article>
          ))
        ) : (
          <Unavailable>No correction records supplied.</Unavailable>
        )}
        {publication?.revision && (
          <Link
            className="source-link"
            href={`/events/${encodeURIComponent(event.id)}?date=${event.date}&revision=${encodeURIComponent(publication.revision)}`}
          >
            Permalink to revision {publication.revision}
            <ArrowUpRight size={14} />
          </Link>
        )}
      </section>
    </div>
  );
}
