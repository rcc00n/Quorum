"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Brand } from "./brand";
import { session } from "@/lib/api";
import type { Snapshot } from "@/lib/api";
import type { ReasoningStory, ReasoningRun } from "@/lib/reasoning";
import {
  ReasoningEvidence,
  Sources,
  ClaimReference,
} from "./reasoning-evidence";
import { ReasoningSpectrum } from "./reasoning-spectrum";
import { ReasoningTimeline, previewHref } from "./reasoning-timeline";
function Impact({ story: s }: { story: ReasoningStory }) {
  return (
    <details className="r-impact">
      <summary>Impact {s.rubric.total} / 9 · open the supplied rubric</summary>
      <dl>
        {(
          ["legal_force", "reach", "irreversibility", "confirmation"] as const
        ).map((k) => (
          <div key={k}>
            <dt>
              {k.replaceAll("_", " ")} <strong>{s.rubric[k]}</strong>
            </dt>
            <dd>{s.rubric.rationale[k] || "Rationale not supplied."}</dd>
          </div>
        ))}
      </dl>
      <p className="help">
        Upstream score, not coverage volume. The portal does not score or
        re-rank events.
      </p>
    </details>
  );
}
function Article({ story: s }: { story: ReasoningStory }) {
  return (
    <article className="r-article" aria-label="Reasoning article">
      <p className="eyebrow">
        STORY / {s.event_id} · {s.reading_minutes} MIN READ
      </p>
      <h1>{s.headline}</h1>
      <p className="r-standfirst">{s.standfirst}</p>
      <p className="help">
        Sources follow each passage. Statements remain attributed; uncertainty
        is explicit. This is fictional recorded output.
      </p>
      {(s.needs_review || s.critic_notes || s.review_reason) && (
        <aside className="r-disagreement">
          <strong>
            {s.needs_review ? "Needs review" : "Critic notes supplied"}
          </strong>
          <p>{s.review_reason}</p>
          <p>{s.critic_notes}</p>
        </aside>
      )}
      {s.photo && (
        <p className="r-unavailable">
          Photo withheld: the preview has no independently verified image
          rights/source record.
        </p>
      )}
      <div className="r-prose">
        {s.article.map((b, i) => (
          <div className={"r-paragraph r-kind-" + b.kind} key={i}>
            {b.kind === "context" && (
              <p className="help">
                Source-attributed context · not promoted to an established fact
                by the adapter.
              </p>
            )}
            {b.kind === "statements" && (
              <p className="r-passage-label">Attributed statements</p>
            )}
            <p>{b.text}</p>
            <Sources sources={b.sources} />
            <span className="r-claim-links">
              {b.claim_ids.map((id, index) => (
                <ClaimReference key={id} id={id}>
                  Evidence {index + 1}
                  <span className="sr-only"> for claim {id}</span>
                </ClaimReference>
              ))}
            </span>
          </div>
        ))}
      </div>
      <Impact story={s} />
      <p className="help">
        {s.drafts !== undefined ? `${s.drafts} drafts recorded. ` : ""}
        Post-publication correction history is not supplied. Draft iterations
        are not publication corrections.
      </p>
      <nav className="r-analysis-nav" aria-label="Deeper analysis">
        <a href="#reasoning-evidence">Evidence Explorer ↓</a>
        <a href="#reasoning-perspectives">Across the spectrum ↓</a>
        <a href="#reasoning-timeline">Recorded investigation ↓</a>
      </nav>
    </article>
  );
}
function Roundup({ run }: { run: ReasoningRun }) {
  return (
    <section className="r-section" aria-label="Also today">
      <p className="eyebrow">BELOW THE IMPACT BAR</p>
      <h2>Also today</h2>
      <p>
        {run.roundup.count} events in the supplied roundup. Statuses and sources
        are preserved.
      </p>
      {run.roundup.groups.map((g, index) => (
        <div className="r-roundup-group" key={index}>
          <h3>{g.name}</h3>
          {g.items.map((item) => (
            <article className="r-roundup-row" key={item.event_id}>
              <Link href={previewHref(run, item.event_id)}>{item.line}</Link>
              <p className="help">
                {item.status}
                {item.needs_review ? " · needs review" : ""}
              </p>
              <Sources sources={item.sources} />
            </article>
          ))}
        </div>
      ))}
      {!run.roundup.groups.length && <p>No roundup entries supplied.</p>}
    </section>
  );
}
export function ReasoningPreviewPage({
  eventId,
  day,
  version,
}: {
  eventId: string;
  day: string;
  version: string;
}) {
  const router = useRouter();
  const [data, setData] = useState<Snapshot | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const s = await session();
      if (!s.user) {
        router.replace("/login");
        return;
      }
      const query = new URLSearchParams();
      if (day) query.set("date", day);
      if (version) query.set("version", version);
      const response = await fetch("/api/preview/reasoning/?" + query, {
        cache: "no-store",
        credentials: "same-origin",
      });
      const json = await response.json();
      if (!response.ok) throw Error(json.error || "Preview unavailable.");
      setData(json);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [router, day, version]);
  useEffect(() => {
    void load();
  }, [load]);
  const run = data?.reasoning,
    story = run?.stories.find((s) => s.event_id === eventId),
    roundup = run?.roundup.groups
      .flatMap((g) => g.items)
      .find((i) => i.event_id === eventId);
  return (
    <div className="r-preview">
      <header className="r-header">
        <Brand />
        <nav aria-label="Preview navigation">
          <Link href="/dashboard">Your portal</Link>
          {run && <Link href={previewHref(run)}>Topic edition</Link>}
        </nav>
      </header>
      <div className="r-demo" role="note">
        <strong>DEMO / FICTIONAL DATA</strong>
        <span>
          Recorded development sample · not real news, live inference or
          publication-grade evidence.
        </span>
      </div>
      <main id="main" className="r-main">
        {loading ? (
          <p role="status">Loading the recorded reasoning sample…</p>
        ) : error ? (
          <section role="alert">
            <h1>Reasoning preview unavailable</h1>
            <p>{error}</p>
            <p>
              Use the explicitly enabled localhost development preview. This
              page never falls back to a fictional production feed.
            </p>
            <button className="button" onClick={load}>
              Try again
            </button>
          </section>
        ) : run && data?.preview ? (
          <>
            <div className="r-edition-meta">
              <span>
                Edition {run.edition_date} · version {run.version} · reasoning{" "}
                {run.schema_version}
              </span>
              <span>
                {data.preview.status === "partial"
                  ? "Partial recorded result"
                  : run.status === "empty"
                    ? "Completed empty selection"
                    : "Completed recorded result"}
              </span>
            </div>
            <p className="r-preview-limits">
              Not published · freshness unknown: no generated, expiry or
              publication timestamps supplied.
            </p>
            {(run.status === "partial" ||
              run.errors?.length ||
              run.sources_missing.length > 0) && (
              <aside className="r-disagreement" role="status">
                <strong>This preview is incomplete</strong>
                <p>
                  Missing sources:{" "}
                  {run.sources_missing.join(", ") || "None listed"}
                </p>
                {run.errors?.map((e, i) => (
                  <p key={i}>{e}</p>
                ))}
              </aside>
            )}
            {eventId ? (
              story ? (
                <>
                  <Article story={story} />
                  <ReasoningEvidence story={story} />
                  <ReasoningSpectrum
                    story={story}
                    sources={
                      data.events.find((e) => e.id === eventId)?.sources || []
                    }
                  />
                </>
              ) : roundup ? (
                <section className="r-section">
                  <p className="eyebrow">ROUNDUP EVENT / {roundup.event_id}</p>
                  <h1>{roundup.line}</h1>
                  <p>
                    {roundup.status}
                    {roundup.needs_review ? " · needs review" : ""}
                  </p>
                  <Sources sources={roundup.sources} />
                  <p className="r-unavailable">
                    Only a roundup entry was supplied. No full article or claim
                    evidence is available for this event; recorded event steps
                    are below.
                  </p>
                </section>
              ) : (
                <section>
                  <h1>This event is not in the preview</h1>
                  <Link href={previewHref(run)}>
                    Return to the supplied edition →
                  </Link>
                </section>
              )
            ) : (
              <>
                <section className="r-topic">
                  <p className="eyebrow">TOPIC EDITION / {run.topic_id}</p>
                  <h1>The daily perspective</h1>
                  <p className="r-topic-summary">{run.summary}</p>
                  <p className="help">
                    {run.bar
                      ? `Impact bar ${run.bar.threshold} / 9; confirmation minimum ${run.bar.confirmation_min}. `
                      : ""}
                    Up to ten stories; no minimum and no padding.
                  </p>
                  {run.status === "empty" &&
                    !run.stories.length &&
                    data.preview.status !== "partial" && (
                      <aside className="r-quiet" role="status">
                        <h2>No featured stories crossed the bar</h2>
                        <p>
                          This fictional completed run supplied an empty
                          selection, not a missing snapshot.
                        </p>
                      </aside>
                    )}
                  {data.events.map((e) => (
                    <article className="r-story-row" key={e.id}>
                      <p className="eyebrow">
                        {e.reasoning?.rank !== undefined
                          ? String(e.reasoning.rank).padStart(2, "0")
                          : ""}{" "}
                        / IMPACT {e.reasoning?.rubric.total} OF 9
                      </p>
                      <h2>
                        <Link href={previewHref(run, e.id)}>{e.title}</Link>
                      </h2>
                      <p>{e.summary}</p>
                      <p className="help">
                        {e.reasoning?.reading_minutes} min read ·{" "}
                        {e.reasoning?.claims.length} supplied claims
                        {e.reasoning?.needs_review ? " · needs review" : ""}
                      </p>
                    </article>
                  ))}
                </section>
                <Roundup run={run} />
              </>
            )}
            <ReasoningTimeline run={run} />
            <section className="r-section">
              <h2>Preview provenance limits</h2>
              <ul>
                {data.preview.missing_provenance.map((s) => (
                  <li key={s}>{s}: unavailable</li>
                ))}
              </ul>
              {data.preview.warnings.map((w, i) => (
                <p className="help" key={i}>
                  {w}
                </p>
              ))}
              <p className="help">
                Run {run.run_id} · file SHA-256 {data.preview.sha256}. This
                identifies the fixture file, not collected source content.
              </p>
            </section>
          </>
        ) : null}
      </main>
      <footer className="r-footer">
        Quorum · Recorded evidence, open to inspection. Development preview
        only.
      </footer>
    </div>
  );
}
