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
import { Spectrum } from "./spectrum";
import { ReasoningSpectrum } from "./reasoning-spectrum";
import { ReasoningTimeline, previewHref } from "./reasoning-timeline";
import { roundupCheckNotice } from "@/lib/reasoning-trace";
function ReadingNavigation({
  run,
  story,
  eventId,
}: {
  run: ReasoningRun;
  story: boolean;
  eventId: string;
}) {
  const [active, setActive] = useState("");
  const items = story
    ? [
        ["reasoning-article", "Article"],
        ["reasoning-evidence", "Evidence"],
        ["reasoning-timeline", "Agent timeline"],
        ["reasoning-perspectives", "Spectrum"],
      ]
    : [
        ["reasoning-stories", "Stories"],
        ["reasoning-roundup", "Also today"],
        ["reasoning-timeline", "Agent timeline"],
      ];
  const ids = items.map(([id]) => id).join(",");
  useEffect(() => {
    const targets = ids
      .split(",")
      .map((id) => document.getElementById(id))
      .filter((e): e is HTMLElement => !!e);
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) setActive(entry.target.id);
      },
      { rootMargin: "-125px 0px -55% 0px" },
    );
    targets.forEach((e) => observer.observe(e));
    // A date/event navigation may render its anchor after the recorded edition loads.
    const target = document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({ behavior: "instant" });
    return () => observer.disconnect();
  }, [ids, eventId]);
  return (
    <nav className="r-reader-nav" aria-label="Read and investigate">
      {items.map(([id, title]) => (
        <a
          key={id}
          href={"#" + id}
          aria-current={active === id ? "location" : undefined}
          onClick={() => setActive(id)}
        >
          {title}
        </a>
      ))}
      {story && (
        <Link href={previewHref(run) + "#reasoning-roundup"}>Also today ↗</Link>
      )}
    </nav>
  );
}
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
function Article({ story: s, fictional }: { story: ReasoningStory; fictional: boolean }) {
  return (
    <article
      id="reasoning-article"
      className="r-article"
      aria-label="Reasoning article"
    >
      <p className="eyebrow">
        STORY / {s.event_id} · {s.reading_minutes} MIN READ
      </p>
      <h1>{s.headline}</h1>
      <p className="r-standfirst">{s.standfirst}</p>
      <p className="help">
        Sources follow each passage. Statements remain attributed; uncertainty
        is explicit. {fictional ? "This is fictional recorded output." : "This recorded output requires editorial review."}
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
    </article>
  );
}
function Roundup({ run }: { run: ReasoningRun }) {
  return (
    <section
      id="reasoning-roundup"
      className="r-section"
      aria-label="Also today"
    >
      <p className="eyebrow">BELOW THE IMPACT BAR</p>
      <h2>Also today</h2>
      <p>
        {run.roundup.count} events in the supplied roundup. Statuses and sources
        are preserved as producer labels; they do not establish independent verification.
      </p>
      {run.roundup.groups.map((g, index) => (
        <div className="r-roundup-group" key={index}>
          <h3>{g.name}</h3>
          {g.items.map((item) => (
            <article className="r-roundup-row" key={item.event_id}>
              <Link href={previewHref(run, item.event_id)}>{item.line}</Link>
              <p className="help">
                Producer status: {item.status}
                {item.needs_review ? " · needs review" : ""}
              </p>
              <p className="r-check-notice help">{roundupCheckNotice(run.trace, item.event_id)}</p>
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
      <div className="r-preview-chrome">
        <div className="r-demo" role="note">
          <strong>{!run ? "UNPUBLISHED PREVIEW" : run.provenance.fictional ? "DEMO / FICTIONAL DATA" : "UNPUBLISHED / CORPUS EXPERIMENT"}</strong>
          <span>{!run ? "Recorded snapshot · awaiting provenance." : run.provenance.fictional ? "Recorded snapshot · not real news or live inference." : run.provenance.model === "stand-ins" ? "Producer-declared collected corpus · deterministic stand-ins · no AI verification." : "Producer-declared collected corpus · recorded model output · requires editorial review."}</span>
        </div>
        {run && !loading && !error && (
          <ReadingNavigation run={run} story={!!story} eventId={eventId} />
        )}
      </div>
      <main id="main" className="r-main">
        {loading ? (
          <section className="r-preview-loading" role="status" aria-busy="true">
            <p>Loading the recorded reasoning sample…</p>
            <span />
            <span />
            <span />
          </section>
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
              {run.published_at === null
                ? "Not published"
                : `Reported publication: ${run.published_at} (unverified)`}
              {" · "}Generated {run.generated_at}
              {" · "}
              {data.preview.expiry_hint === "expired"
                ? "Expired hint"
                : "Expiry hint"}
              : {run.expires_at}. Edition timezone: {run.edition_timezone}.
              Recorded window: {run.window.start} → {run.window.end}. Declared
              corpus: {run.provenance.corpus}; model: {run.provenance.model}.{" "}
              These declarations do not establish a genuine sponsor run or
              publication.
            </p>
            {data.preview.provisional && !data.preview.corpus_binding && (
              <p className="r-preview-limits r-corpus-binding">
                PROVISIONAL CORPUS · Capture metadata unavailable; no sidecar is bound to this preview.
              </p>
            )}
            {data.preview.corpus_binding && (
              <p className="r-preview-limits r-corpus-binding">
                {data.preview.corpus_binding.provisional ? "PROVISIONAL CORPUS" : "Producer corpus capture"}
                {" · "}As of {data.preview.corpus_binding.corpus_as_of_utc}.
                {" "}Sidecar bound to these snapshot bytes; execution and corpus manifests remain producer declarations.
              </p>
            )}
            {(run.provenance.fact_checker_model !== undefined ||
              run.provenance.model_calls !== undefined ||
              run.provenance.answered_by !== undefined ||
              run.provenance.model_errors !== undefined) && (
              <p className="r-preview-limits r-model-provenance">
                Reported model provenance: {run.provenance.fact_checker_model !== undefined &&
                  `fact-checker ${run.provenance.fact_checker_model}. `}
                {run.provenance.model_calls !== undefined &&
                  `${run.provenance.model_calls} model calls. `}
                {run.provenance.model_errors !== undefined &&
                  `${run.provenance.model_errors} model errors. `}
                {run.provenance.answered_by !== undefined &&
                  `Answered by: ${Object.entries(run.provenance.answered_by)
                    .map(([model, count]) => `${model} ×${count}`)
                    .join(", ")}. `}
                Snapshot declarations; not independent provider verification.
              </p>
            )}
            {(run.status === "partial" ||
              run.errors?.length ||
              run.sources_missing.length > 0) && (
              <aside className="r-disagreement" role="status">
                <strong>This preview is incomplete</strong>
                <p>
                  Missing sources:{" "}
                  {run.sources_missing.join(", ") || "None listed"}
                </p>
                {!!run.errors?.length && (
                  <details className="r-upstream-errors">
                    <summary>{run.errors.length} recorded upstream errors · inspect safe diagnostics</summary>
                    {run.errors.map((e, i) => (
                      <p key={i}>
                        {typeof e === "string" ? e : `${e.node}${e.event_id ? ` · ${e.event_id}` : ""}: ${e.message}`}
                      </p>
                    ))}
                  </details>
                )}
              </aside>
            )}
            {eventId ? (
              story ? (
                <>
                  <Article story={story} fictional={run.provenance.fictional} />
                  <ReasoningEvidence story={story} fictional={run.provenance.fictional} />
                  <ReasoningTimeline
                    key={eventId}
                    run={run}
                    currentEvent={eventId}
                  />
                  <ReasoningSpectrum
                    story={story}
                    sources={
                      data.events.find((e) => e.id === eventId)?.sources || []
                    }
                  />
                  <div className="r-next-reading">
                    <span>Continue with the rest of the edition</span>
                    <Link href={previewHref(run) + "#reasoning-roundup"}>
                      Also today →
                    </Link>
                  </div>
                </>
              ) : roundup ? (
                <section className="r-section">
                  <p className="eyebrow">ROUNDUP EVENT / {roundup.event_id}</p>
                  <h1>{roundup.line}</h1>
                  <p>
                    Producer status: {roundup.status}
                    {roundup.needs_review ? " · needs review" : ""}
                  </p>
                  <p className="r-check-notice help">{roundupCheckNotice(run.trace, roundup.event_id)}</p>
                  {roundup.line_source === "title" && <p className="help">Source headline fallback; no generated roundup line was supplied.</p>}
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
                <section id="reasoning-stories" className="r-topic">
                  <p className="eyebrow">TOPIC EDITION / {run.topic_id}</p>
                  <h1>The daily perspective</h1>
                  <p className="r-topic-summary">{run.summary}</p>
                  {run.summary_source === "fallback" && <p className="r-unavailable">Producer supplied a fallback summary; inspect the partial-run errors.</p>}
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
                          This {run.provenance.fictional ? "fictional " : ""}completed run supplied an empty
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
            {!story && (
              <ReasoningTimeline
                key={eventId}
                run={run}
                currentEvent={eventId}
              />
            )}
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
                identifies the snapshot file, not collected source content.
              </p>
            </section>
          </>
        ) : null}
        {data?.catalog_revision && !loading && !error && !eventId && <section className="r-section registry-catalog">
          <h2>Source registry</h2><p>Real catalog definitions · revision {data.catalog_revision}. Ratings describe sources, not verification of this snapshot. Producer cohort counts remain unchanged.</p>
          <Spectrum sources={data.sources} />
        </section>}
      </main>
      <footer className="r-footer">
        Quorum · Recorded evidence, open to inspection. Development preview
        only.
      </footer>
    </div>
  );
}
