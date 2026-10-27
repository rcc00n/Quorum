"use client";
import Link from "next/link";
import { useState } from "react";
import type { Event, Snapshot } from "@/lib/api";
import { safeUrl } from "@/lib/api";
import { isQuietDay, licensedPhoto, readableArticle } from "@/lib/editorial";
import { RoundupGroup } from "./roundup-group";
import { ReviewLabel } from "./story";
import type { EditorialPhoto, EditionPresentation } from "@/lib/editorial";
function Photo({ photo }: { photo: EditorialPhoto }) {
  const [failed, setFailed] = useState(false);
  if (failed || !licensedPhoto(photo)) return null;
  return (
    <figure className="editorial-photo">
      <img
        src={photo.url}
        alt={photo.caption}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
      <figcaption>
        {photo.caption} ·{" "}
        <a href={photo.source_url} target="_blank" rel="noopener noreferrer">
          {photo.credit}
        </a>{" "}
        ·{" "}
        <a href={photo.license_url} target="_blank" rel="noopener noreferrer">
          {photo.license}
        </a>
      </figcaption>
    </figure>
  );
}
export function StoryArticle({ event }: { event: Event }) {
  if (!readableArticle(event)) return null;
  const article = event.article!,
    claims = event.analysis!.claims,
    docs = event.analysis!.documents;
  return (
    <article className="story-prose" aria-label="Source-backed article">
      <p className="help">
        Facts carry source links. Statements name their speaker. Unconfirmed
        claims follow last.
        {article.reading_minutes &&
        Number.isFinite(article.reading_minutes) &&
        article.reading_minutes > 0
          ? ` ${article.reading_minutes} min read.`
          : ""}
      </p>
      {article.photo && <Photo photo={article.photo} />}
      {article.paragraphs.map((p, index) => {
        const refs = claims.filter((c) => p.claim_ids.includes(c.id));
        const cited = new Set(
          refs.flatMap((c) =>
            [...c.supporting, ...c.contradicting].map((r) => r.document_id),
          ),
        );
        return (
          <div key={index} className="story-paragraph">
            {p.kind === "not_confirmed" && (
              <span className="eyebrow">Not confirmed</span>
            )}
            {p.kind === "statement" && (
              <small className="article-attribution">
                {[...new Set(refs.map((c) => c.attribution?.speaker))].join(
                  " · ",
                )}
              </small>
            )}
            <p>{p.text}</p>
            <div className="article-references">
              {docs
                .filter((d) => cited.has(d.id))
                .map(
                  (d) =>
                    safeUrl(d.url) && (
                      <a
                        key={d.id}
                        href={safeUrl(d.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {d.title}
                      </a>
                    ),
                )}
              {refs.map((c) => (
                <a key={c.id} href={"#claim-" + c.id}>
                  Evidence
                </a>
              ))}
            </div>
          </div>
        );
      })}
      <p className="appendix-intro">
        Across the spectrum · Evidence and investigation
      </p>
    </article>
  );
}
export function EditionNotes({
  snapshot,
  day,
  topic,
  followed,
  roundup = true,
}: {
  snapshot: Snapshot;
  day: string;
  topic: string;
  followed: string[];
  roundup?: boolean;
}) {
  if (
    !snapshot.publication ||
    ["pending", "error"].includes(snapshot.publication.status) ||
    ["pending", "error"].includes(snapshot.status)
  )
    return null;
  const names = new Map((snapshot.topics ?? []).map((t) => [t.id, t.name]));
  // On Home the topics follow the reader's topic order, the board's order above them (2026-10-27).
  const order = (id: string) => (topic ? 0 : followed.indexOf(id));
  const editions = (snapshot.editions ?? [])
    .filter(
      (e) =>
        e.date === day &&
        (topic ? e.topic_id === topic : followed.includes(e.topic_id)),
    )
    .sort((a, b) => order(a.topic_id) - order(b.topic_id));
  if (!roundup)
    return (
      <>
        {editions.map((e) => (
          <EditionNote key={e.topic_id} snapshot={snapshot} edition={e} />
        ))}
      </>
    );
  // DECISION(2026-10-27, Anastasia/Claude Code; supersedes the per-topic "Also today · <topic>" blocks of the same
  // evening): Home carries one "Also today" section under the board: one heading and one help line, then every
  // followed topic with an edition as a subsection headed by the topic's name (anchor also-today-<topic id>, which
  // the board's "N events below the bar" card links to), its digest sentence and its status groups; no quiet-day
  // panel here, the board's quiet card says it. Why: Anastasia, 27 October: with three topics the page showed three
  // "Also today" sections one after another; the roundup is one section, the topics are its parts.
  const shown = editions.filter((e) => e.roundup.length || e.summary);
  if (!shown.length) return null;
  return (
    <section className="edition-notes" aria-label="Edition context">
      <section aria-label="Also today" className="also-today">
        <h3>Also today</h3>
        {shown.some((e) => e.roundup.length) && (
          <p className="help">
            Other events in this edition · source and status supplied by the
            analysis.
          </p>
        )}
        {shown.map((e) => (
          <AlsoTodayTopic
            key={e.topic_id}
            edition={e}
            name={names.get(e.topic_id) || e.topic_id}
          />
        ))}
      </section>
    </section>
  );
}
function EditionNote({
  snapshot,
  edition: e,
}: {
  snapshot: Snapshot;
  edition: EditionPresentation;
}) {
  // The topic page shows the digest sentence and the quiet day but not "Also today", which stays on Home
  // (Anastasia, second cabinet pass 2026-10-27).
  return (
    <section className="edition-notes" aria-label="Edition context">
      {isQuietDay(snapshot, e) && (
        <div className="quiet-day" role="status">
          <h3>A quiet day for major stories</h3>
          <p>
            Processing completed. No story crossed the impact bar for this topic
            and edition.
          </p>
        </div>
      )}
      {!!e.summary && <p>{e.summary}</p>}
    </section>
  );
}
function AlsoTodayTopic({ edition: e, name }: { edition: EditionPresentation; name: string }) {
  const headingId = `also-today-${e.topic_id}-name`;
  return (
    <div className="also-today-topic" id={`also-today-${e.topic_id}`} role="group" aria-labelledby={headingId}>
      <h4 id={headingId}>{name}</h4>
      {!!e.summary && <p className="edition-digest">{e.summary}</p>}
      {e.completion === "partial" && (
        <p className="help">This roundup is incomplete.</p>
      )}
      {e.roundup.map((group, index) => (
        // The group folds past three events (components/roundup-group.tsx, Anastasia's cabinet pass 2026-10-27).
        <RoundupGroup key={index} name={group.name}>
          {group.items.map((item, i) => (
            <div className="roundup-item" key={i}>
              <p>{item.text}</p>
              <small>
                {item.label
                  ? item.label.charAt(0).toUpperCase() + item.label.slice(1)
                  : item.status === "attributed"
                  ? "Attributed statement"
                  : item.status === "established"
                    ? "Established"
                    : item.status === "disputed"
                      ? "Disputed"
                      : "Unknown"}
              </small>
              {/* The producer's flags on a roundup line (2026-10-27, Anastasia/Claude Code; master's consistency
                  check of the edition output path): an escalated event reaches the roundup flagged needs_review
                  (ARCHITECTURE § 5) and is shown with the story's label, never silently; a raw-title fallback line
                  says so in the preview's words (reasoning-preview.tsx), since the producer marks it (B10). */}
              {item.needs_review && <ReviewLabel />}
              {item.line_source === "title" && (
                <p className="help">Source headline fallback; no generated roundup line was supplied.</p>
              )}
              <div className="article-references">
                {item.sources.map(
                  (s, j) =>
                    safeUrl(s.url) && (
                      <a
                        href={safeUrl(s.url)}
                        key={j}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {s.title}
                      </a>
                    ),
                )}
                {item.event_id && (
                  <Link
                    href={
                      "/events/" +
                      encodeURIComponent(item.event_id) +
                      "?date=" +
                      e.date
                    }
                  >
                    View evidence →
                  </Link>
                )}
              </div>
            </div>
          ))}
        </RoundupGroup>
      ))}
    </div>
  );
}
