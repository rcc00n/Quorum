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
      onClick={() => {
        const el = document.getElementById(
          "reasoning-claim-" + id,
        ) as HTMLDetailsElement | null;
        if (el) {
          el.open = true;
          el.querySelector("summary")?.focus();
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
      <p className="eyebrow">{title}</p>
      <h4>{verdict}</h4>
      <p className="help">
        Separate review reason and review timestamp not supplied.
      </p>
      {evidence.length ? (
        evidence.map((e, i) => (
          <div
            className="r-evidence"
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
          <small>
            {c.kind === "statement" ? "Attributed statement · " : ""}
            {c.status}
          </small>
          <strong>{c.text}</strong>
        </span>
        <span aria-hidden="true">+</span>
      </summary>
      <div className="r-claim-body">
        {c.speaker && (
          <p>
            Speaker: {c.speaker}. Attribution does not establish the statement’s
            truth.
          </p>
        )}
        {c.verifier !== c.fact_checker && (
          <p className="r-disagreement" role="note">
            The two reviewers disagree: primary {c.verifier}, independent{" "}
            {c.fact_checker}. Final status: {c.status}.
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
              </div>
            ))}
          </section>
        )}
        <div className="r-final">
          <small>Final {c.status} · supplied adjudication</small>
          <p>{c.reason || "No final rationale supplied."}</p>
        </div>
        <p className="help">
          Review independence is separate from source independence. Original
          document IDs, content hashes, quote offsets, achieved access levels
          and review timestamps are unavailable in this preview.
        </p>
      </div>
    </details>
  );
}
export function ReasoningEvidence({ story }: { story: ReasoningStory }) {
  return (
    <section id="reasoning-evidence" className="r-section">
      <p className="eyebrow">FOLLOW THE EVIDENCE</p>
      <h2>Evidence Explorer</h2>
      <p>
        Compare the recorded primary and blind fact-checking paths. These
        fictional findings are not independently verified.
      </p>
      {story.claims.map((c) => (
        <ClaimChains key={c.id} claim={c} />
      ))}
    </section>
  );
}
