"use client";
import Link from "next/link";
import { useState } from "react";
import type { Event, Snapshot } from "@/lib/api";
import { safeUrl } from "@/lib/api";
import { isQuietDay, licensedPhoto, readableArticle } from "@/lib/editorial";
import { RoundupGroup } from "./roundup-group";
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
  return (
    <>
      {snapshot.editions
        ?.filter(
          (e) =>
            e.date === day &&
            (topic ? e.topic_id === topic : followed.includes(e.topic_id)),
        )
        .map((e) => (
          <EditionNote key={e.topic_id} snapshot={snapshot} edition={e} roundup={roundup} />
        ))}
    </>
  );
}
function EditionNote({
  snapshot,
  edition: e,
  roundup = true,
}: {
  snapshot: Snapshot;
  edition: EditionPresentation;
  // The topic page shows the digest sentence and the quiet day but not "Also today", which stays on Home
  // (Anastasia, second cabinet pass 2026-10-27).
  roundup?: boolean;
}) {
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
      {roundup && !!e.roundup.length && (
        <section aria-label="Also today">
          <h3>Also today</h3>
          <p className="help">
            Other events in this edition · source and status supplied by the
            analysis.
          </p>
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
        </section>
      )}
    </section>
  );
}
