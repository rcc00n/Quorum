"use client";
import type {
  ReasoningStory,
  ReasoningClaim,
  ReasoningEvidence,
  ReasoningSource,
} from "@/lib/reasoning";
import { safeUrl } from "@/lib/api";
export function Sources({ sources }: { sources: ReasoningSource[] }) {
  return (
    <span className="r-sources">
      {[...new Map(sources.map((s) => [s.url, s])).values()].map(
        (s) =>
          safeUrl(s.url) && (
            <a
              key={s.url}
              href={safeUrl(s.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {s.title} ↗
            </a>
          ),
      )}
    </span>
  );
}
export function ClaimReference({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={"#reasoning-claim-" + id}
      onClick={(event) => {
        const el = document.getElementById(
          "reasoning-claim-" + id,
        ) as HTMLDetailsElement | null;
        if (el) {
          event.preventDefault();
          el.open = true;
          history.replaceState(history.state, "", "#reasoning-claim-" + id);
          el.querySelector("summary")?.focus({ preventScroll: true });
          el.scrollIntoView({
            block: "start",
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
              ? "instant"
              : "smooth",
          });
        }
      }}
    >
      {children}
    </a>
  );
}
function Chain({
  title,
  verdict,
  evidence,
}: {
  title: string;
  verdict: string;
  evidence: ReasoningEvidence[];
}) {
  return (
    <section className="r-chain">
      <header className="r-review-heading">
        <p className="eyebrow">{title}</p>
        <h4>{verdict}</h4>
        <p className="r-evidence-counts">
          {evidence.length} evidence {evidence.length === 1 ? "row" : "rows"}
          {(["supports", "contradicts", "neutral", "statement"] as const).map(
            (stance) => {
              const count = evidence.filter((e) => e.stance === stance).length;
              return count ? (
                <span key={stance}>
                  {count}{" "}
                  {
                    {
                      supports: "supporting",
                      contradicts: "contradicting",
                      neutral: "neutral",
                      statement: "attributed",
                    }[stance]
                  }
                </span>
              ) : null;
            },
          )}
        </p>
      </header>
      {evidence.length ? (
        evidence.map((e, i) => (
          <div
            className={"r-evidence r-stance-" + e.stance}
            key={i}
            style={
              { "--reveal": Math.min(i, 5) * 35 + "ms" } as React.CSSProperties
            }
          >
            <p className="r-stance">
              {e.stance === "supports"
                ? "Supporting evidence"
                : e.stance === "contradicts"
                  ? "Contradicting evidence"
                  : e.stance === "statement"
                    ? "Attributed statement"
                    : "Neutral evidence"}
            </p>
            <blockquote>{e.quote}</blockquote>
            <Sources sources={[e]} />
            {e.by_headline !== undefined && (
              <p className="help">{e.by_headline ? "Headline and lead only (producer flag)." : "Producer did not mark headline-only access; body access is not independently verified."}</p>
            )}
            {e.source_id && <details><summary>Reported quote provenance</summary>
              <p>Source: {e.source_id} · {e.official_doc_id != null ? `Official document: ${e.official_doc_id}` : `Article document: ${e.document_id ?? "unavailable"}`}</p>
              <p>Access: {e.access_achieved ?? "unavailable"} · Fetched: {e.fetched_at ?? "unavailable"}{e.from_previous_day ? " · Earlier edition context" : ""}</p>
              <p>Unicode quote range: {e.char_start ?? "unavailable"}–{e.char_end ?? "unavailable"} (end exclusive). Content hash: {e.content_hash_at_quote ?? "unavailable"}</p>
              <p>{e.hash_mismatch === true ? "Reported content version mismatch; requires review." : "Producer declarations; source text and quote binding are not independently verified by this preview."}</p>
            </details>}
            <small>
              Source independence group:{" "}
              {e.independence_group || "Not supplied"} ·{" "}
              {e.is_document === true
                ? "Document evidence (upstream flag)"
                : e.is_document === false
                  ? "Publication / statement"
                  : "Document type unavailable"}
            </small>
          </div>
        ))
      ) : (
        <p className="r-unavailable">
          No evidence assigned to this review in the snapshot.
        </p>
      )}
    </section>
  );
}
export function ClaimChains({ claim: c }: { claim: ReasoningClaim }) {
  const primary = c.evidence.filter(
      (e) => e.found_by === "researcher" || e.found_by === "verifier",
    ),
    independent = c.evidence.filter((e) => e.found_by === "fact_checker"),
    unassigned = c.evidence.filter((e) => !e.found_by);
  return (
    <details className="r-claim" id={"reasoning-claim-" + c.id}>
      <summary>
        <span>
          <small className="r-claim-status">
            {c.kind === "statement" ? "Attributed statement · " : ""}
            {c.kind === "context" ? "Source-attributed context · " : ""}
            {c.status}
          </small>
          <strong>{c.text}</strong>
          <span className="r-agreement">
            {c.verifier === c.fact_checker
              ? "Reviewers agree"
              : "Reviewers disagree"}{" "}
            · {c.evidence.length} evidence rows
          </span>
        </span>
        <span className="r-disclosure-icon" aria-hidden="true">
          +
        </span>
      </summary>
      <div className="r-claim-body">
        <div className="r-final">
          <div>
            <small>Final claim status</small>
            <strong>{c.status}</strong>
          </div>
          <div>
            <small>Supplied adjudication</small>
            <p>{c.reason || "No final rationale supplied."}</p>
          </div>
        </div>
        {c.resolved_by && <aside className="r-disagreement">
          <strong>Resolution: {c.resolved_by}</strong>
          {/* DECISION(2026-10-25, rcc00n/Codex): distinguish a reviewer proposal from the accepted final verdict.
              Why: genuine v4 includes proposals rejected by producer code despite a confirmed reviewer response. */}
          <p>Third reviewer proposal: {c.reviewer_status ?? "No verdict supplied"}</p>
          {c.reviewer_status && c.resolved_by !== "reviewer" && <p className="r-review-proposal-rejected">Proposal not adopted; the final claim status above remains authoritative.</p>}
          {c.reviewer_reason && <p>{c.reviewer_reason}</p>}
          {c.reviewer_quote && <blockquote>{c.reviewer_quote}</blockquote>}
          <p>Recorded producer decision; not an independent portal review.</p>
        </aside>}
        {c.speaker && (
          <p>
            Speaker: {c.speaker}. Attribution does not establish the statement’s
            truth.
          </p>
        )}
        <div className="r-chains">
          <Chain
            title="Primary verifier / researcher"
            verdict={c.verifier}
            evidence={primary}
          />
          <Chain
            title="Independent fact-checker"
            verdict={c.fact_checker}
            evidence={independent}
          />
        </div>
        {!!unassigned.length && (
          <section>
            <h4>Review assignment unavailable</h4>
            <p>
              These evidence rows have no found_by value and are not assigned to
              either reviewer.
            </p>
            {unassigned.map((e, i) => (
              <div key={i}>
                <p>
                  {e.stance}: {e.quote}
                </p>
                <Sources sources={[e]} />
            {e.by_headline !== undefined && (
              <p className="help">{e.by_headline ? "Headline and lead only (producer flag)." : "Producer did not mark headline-only access; body access is not independently verified."}</p>
            )}
              </div>
            ))}
          </section>
        )}
        <p className="help">
          Review independence is separate from source independence. Original
          document IDs, content hashes, quote offsets, achieved access levels
          and review timestamps are unavailable in this preview. Separate review
          reasons are not supplied.
        </p>
        <a className="r-return-link" href="#reasoning-article">
          Back to article ↑
        </a>
      </div>
    </details>
  );
}
export function ReasoningEvidence({ story, fictional = true }: { story: ReasoningStory; fictional?: boolean }) {
  return (
    <section id="reasoning-evidence" className="r-section">
      <p className="eyebrow">FOLLOW THE EVIDENCE</p>
      <h2>Evidence Explorer</h2>
      <p>
        Compare the recorded primary and blind fact-checking paths. These
        {fictional ? "fictional" : "recorded"} findings are not independently verified.
      </p>
      <div className="r-evidence-guide">
        <span>
          {story.claims.length} claims ·{" "}
          {story.claims.filter((c) => c.verifier !== c.fact_checker).length}{" "}
          reviewer{" "}
          {story.claims.filter((c) => c.verifier !== c.fact_checker).length ===
          1
            ? "disagreement"
            : "disagreements"}
        </span>
        {story.claims.find((c) => c.verifier !== c.fact_checker) && (
          <ClaimReference
            id={story.claims.find((c) => c.verifier !== c.fact_checker)!.id}
          >
            Inspect a disagreement ↓
          </ClaimReference>
        )}
      </div>
      {story.claims.map((c) => (
        <ClaimChains key={c.id} claim={c} />
      ))}
    </section>
  );
}
