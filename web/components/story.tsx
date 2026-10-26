"use client";
import Link from "next/link";
import { Fragment, useState } from "react";
import type { Event, Source, Topic } from "@/lib/api";
import { rating, cohort, safeUrl } from "@/lib/api";
import type { Claim, Document, StructuredAnalysis } from "@/lib/analysis";
import type { EditorialPhoto } from "@/lib/editorial";
import { licensedPhoto, readableArticle } from "@/lib/editorial";
import "@/app/story.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the story page (an event whose reasoning output supplied article
// paragraphs) is laid out as a printed page: the breadcrumb and the lead photo on the page column, every text
// element on a centred 560 px measure, the facts as plain text with their sources as small grey words after the
// paragraph, statements attributed inside the sentence, "Not confirmed." as the one run-in, a hairline, then the
// appendix head over the workspace's own sections. The page composes no prose: every string is a snapshot field,
// a counted number or one of the constants below (Yelysei's to approve). Why: Anastasia's brief of 2026-10-26
// (the prototype's indentation and ease of reading, in our identity), Yelysei's story-page specification and
// docs/DECISIONS.md › Stories as articles; the design panel's verdict is in web/DESIGN.md › Decisions.

const KEY_LINE =
  "Plain text is a confirmed fact with its sources after it. A statement is attributed in the sentence itself. What is not confirmed is listed at the end. No evaluation is added.";
const SAYS = "says";
const STATUS_WORDS: Record<string, string> = { disputed: "disputed", unknown: "unknown" };
const RUN_IN = "Not confirmed.";
const APPENDIX_TITLE = "Across the spectrum";
const APPENDIX_TAIL = " · Evidence and investigation";
const APPENDIX_SUB = "How the outlets told this story, every claim with its evidence, and the trace of the investigation.";
const CRUMB_FALLBACK = "Today";

type Paragraph = NonNullable<Event["article"]>["paragraphs"][number];
type Mark = { kind: "word" | "source" | "key"; text: string; href?: string; title?: string; sep: boolean };

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

// The Evidence Explorer's numbering, shared with its rows so the key in the text and the row carry one number.
export function claimKey(index: number) {
  return String(index + 1).padStart(2, "0");
}

function formatDate(iso: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function StoryCrumb({ topic, date }: { topic: Topic | null; date?: string }) {
  const href = topic ? `/topics/${encodeURIComponent(topic.id)}${date ? `?date=${date}` : ""}` : "/dashboard";
  return (
    <nav className="story-crumb" aria-label="Topic">
      <Link href={href}>
        <span className="story-crumb-glyph" aria-hidden="true">
          ‹
        </span>
        {topic ? topic.name : CRUMB_FALLBACK}
      </Link>
    </nav>
  );
}

function Photo({ photo }: { photo: EditorialPhoto }) {
  const [failed, setFailed] = useState(false);
  if (failed || !licensedPhoto(photo)) return null;
  const source = safeUrl(photo.source_url);
  const licence = safeUrl(photo.license_url);
  return (
    <figure className="story-photo">
      <div className="story-photo-frame">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={photo.url} alt={photo.caption} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
        {source ? (
          <a className="story-credit" href={source} target="_blank" rel="noopener noreferrer">
            {`Photo: ${photo.credit}`}
          </a>
        ) : (
          <span className="story-credit">{`Photo: ${photo.credit}`}</span>
        )}
      </div>
      <figcaption className="story-caption">
        {photo.caption}
        {" · "}
        {licence ? (
          <a href={licence} target="_blank" rel="noopener noreferrer">
            {photo.license}
          </a>
        ) : (
          photo.license
        )}
      </figcaption>
    </figure>
  );
}

// The marks after a paragraph: speaker words (statements whose sentence lacks the name), then the supporting
// documents (official texts first, one article per independence group, as write.py's claim_sources), then the
// claim keys; after a not-confirmed paragraph only a status word and the key per claim, never an outlet.
function marksFor(p: Paragraph, analysis: StructuredAnalysis, sources: Source[], byId: Map<string, Claim>): Mark[] {
  const claims = p.claim_ids.map((id) => byId.get(id)).filter((c): c is Claim => !!c);
  const marks: Mark[] = [];
  const keyFor = (c: Claim, sep: boolean): Mark | null => {
    const index = analysis.claims.findIndex((x) => x.id === c.id);
    return index < 0 ? null : { kind: "key", text: claimKey(index), href: `#claim-${encodeURIComponent(c.id)}`, title: c.text, sep };
  };
  if (p.kind === "not_confirmed") {
    claims.forEach((c) => {
      marks.push({ kind: "word", text: STATUS_WORDS[c.status] ?? c.status, sep: marks.length > 0 });
      const key = keyFor(c, false);
      if (key) marks.push(key);
    });
    return marks;
  }
  if (p.kind === "statement") {
    const lower = p.text.toLowerCase();
    const speakers = [...new Set(claims.map((c) => c.attribution?.speaker).filter((s): s is string => !!s))];
    speakers.forEach((speaker) => {
      if (!lower.includes(speaker.toLowerCase())) marks.push({ kind: "word", text: `${speaker} ${SAYS}`, sep: marks.length > 0 });
    });
  }
  const docs: Document[] = [];
  claims.forEach((c) =>
    c.supporting.forEach((citation) => {
      const d = analysis.documents.find((x) => x.id === citation.document_id);
      if (d && !docs.includes(d)) docs.push(d);
    }),
  );
  const ordered = [...docs.filter((d) => d.kind === "official"), ...docs.filter((d) => d.kind !== "official")];
  const groups = new Set<string>();
  const labels = new Set<string>();
  ordered.forEach((d) => {
    const source = sources.find((s) => s.id === d.source_id);
    if (d.kind !== "official") {
      const group = source?.independence_group || d.source_id;
      if (groups.has(group)) return;
      groups.add(group);
    }
    const label = d.kind === "official" ? d.title : source?.name || d.title;
    if (labels.has(label)) return;
    labels.add(label);
    const href = safeUrl(d.url);
    marks.push({ kind: href ? "source" : "word", text: label, href, title: d.kind === "official" ? d.title : undefined, sep: marks.length > 0 });
  });
  let first = true;
  claims.forEach((c) => {
    const key = keyFor(c, first && marks.length > 0);
    if (key) {
      marks.push(key);
      first = false;
    }
  });
  return marks;
}

function Marks({ marks }: { marks: Mark[] }) {
  if (!marks.length) return null;
  return (
    <span className="story-marks">
      <span className="story-sr">Sources: </span>
      {marks.map((m, i) => (
        <Fragment key={i}>
          {m.sep && (
            <span className="story-sep" aria-hidden="true">
              {" · "}
            </span>
          )}
          {m.kind === "key" ? (
            <a className="story-key-link" href={m.href} title={m.title}>
              {m.text}
            </a>
          ) : m.kind === "source" ? (
            <a className="story-source" href={m.href} target="_blank" rel="noopener noreferrer" title={m.title}>
              {m.text}
            </a>
          ) : (
            <span className="story-mark-word">{m.text}</span>
          )}
        </Fragment>
      ))}
    </span>
  );
}

// DECISION(2026-10-26, Anastasia/Claude Code): the meta line counts only the claims the article cites, never the
// analysis as a whole, and omits every zero segment. Why: the line describes the story the reader is about to
// read; a claim below the bar or outside the article is the Evidence Explorer's business.
function metaSegments(article: NonNullable<Event["article"]>, byId: Map<string, Claim>) {
  const ids = (kinds: string[]) => new Set(article.paragraphs.filter((p) => kinds.includes(p.kind)).flatMap((p) => p.claim_ids));
  const facts = ids(["fact", "context"]).size;
  const statements = ids(["statement"]).size;
  const open = [...ids(["not_confirmed"])].map((id) => byId.get(id)?.status);
  const disputed = open.filter((s) => s === "disputed").length;
  const unknown = open.filter((s) => s === "unknown").length;
  const segments: string[] = [];
  const minutes = article.reading_minutes;
  if (typeof minutes === "number" && Number.isFinite(minutes) && minutes > 0) segments.push(`${minutes} min read`);
  if (facts) segments.push(plural(facts, "fact confirmed", "facts confirmed"));
  if (statements) segments.push(plural(statements, "statement", "statements"));
  if (disputed) segments.push(`${disputed} disputed`);
  if (unknown) segments.push(`${unknown} not confirmed`);
  return segments;
}

function dataSegments(analysis: StructuredAnalysis, sources: Source[]) {
  const coverage = analysis.coverage;
  const segments: string[] = [];
  if (Array.isArray(coverage.eligible_source_ids)) {
    const eligible = coverage.eligible_source_ids;
    const covered = new Set(coverage.covered_source_ids);
    segments.push(`Covered by ${eligible.filter((id) => covered.has(id)).length} of ${eligible.length} eligible sources`);
    for (const tier of ["major", "minor"] as const) {
      const members = eligible.filter((id) => sources.find((s) => s.id === id)?.tier === tier);
      if (members.length) segments.push(`${members.filter((id) => covered.has(id)).length} of ${members.length} ${tier}`);
    }
  } else {
    if (coverage.publication_count !== null) segments.push(plural(coverage.publication_count, "publication", "publications"));
    if (coverage.independent_confirmation_count !== null)
      segments.push(plural(coverage.independent_confirmation_count, "independent confirmation", "independent confirmations"));
  }
  return segments;
}

// DECISION(2026-10-26, Anastasia/Claude Code): a cohort's silence uses the Perspective Comparison table's own
// definition (eligible sources, the registry tier, the average rating through cohort()), so the line and the
// table never disagree; nothing is shown while eligible_source_ids is null. Why: silence is a visible fact only
// when the eligible set is known.
function silentCohorts(analysis: StructuredAnalysis, sources: Source[]) {
  const eligible = analysis.coverage.eligible_source_ids;
  if (!Array.isArray(eligible)) return [];
  const covered = new Set(analysis.coverage.covered_source_ids);
  const lines: string[] = [];
  for (const [tier, side] of [
    ["major", "Left"],
    ["major", "Right"],
    ["minor", "Left"],
    ["minor", "Right"],
  ] as const) {
    const members = sources.filter((s) => {
      if (!eligible.includes(s.id) || s.tier !== tier) return false;
      const score = rating(s, "average");
      return score !== null && cohort(score) === side;
    });
    if (members.length && members.every((s) => !covered.has(s.id)))
      lines.push(`No ${tier} ${side} outlet covered this story: 0 of ${members.length} eligible, by the average rating.`);
  }
  return lines;
}

function runIn(text: string): [string | null, string] {
  const m = text.match(/^(not confirmed[.:])\s*/i);
  return m ? [m[1], text.slice(m[0].length)] : [null, text];
}

export function Story({ event, sources }: { event: Event; sources: Source[] }) {
  if (!readableArticle(event)) return null;
  const article = event.article!;
  const analysis = event.analysis!;
  const byId = new Map(analysis.claims.map((c) => [c.id, c]));
  const meta = metaSegments(article, byId);
  const data = dataSegments(analysis, sources);
  const silence = silentCohorts(analysis, sources);
  let runInUsed = false;
  return (
    <>
      <article className="story" aria-label="Source-backed article">
        {article.photo && <Photo photo={article.photo} />}
        <time className="story-date" dateTime={event.date}>
          {formatDate(event.date)}
        </time>
        <h1 className="story-headline">{event.title}</h1>
        <p className="story-standfirst">{event.summary}</p>
        {meta.length > 0 && <p className="story-meta">{meta.join(" · ")}</p>}
        <p className="story-key">{KEY_LINE}</p>
        {article.paragraphs.map((p, i) => {
          let lead: string | null = null;
          let text = p.text;
          if (p.kind === "not_confirmed") {
            const [own, rest] = runIn(p.text);
            if (own) {
              lead = own;
              text = rest;
            } else if (!runInUsed) {
              lead = RUN_IN;
            }
            runInUsed = true;
          }
          return (
            <p className="story-p" key={i}>
              {lead && (
                <>
                  <strong className="story-runin">{lead}</strong>{" "}
                </>
              )}
              {text}
              <Marks marks={marksFor(p, analysis, sources, byId)} />
            </p>
          );
        })}
        {silence.map((line) => (
          <p className="story-silence" key={line}>
            {line}
          </p>
        ))}
      </article>
      <hr className="story-end" />
      <div className="story-appendix">
        <h2 className="story-appendix-title">
          {APPENDIX_TITLE}
          <span className="story-appendix-tail">{APPENDIX_TAIL}</span>
        </h2>
        <p className="story-appendix-sub">{APPENDIX_SUB}</p>
        {data.length > 0 && <p className="story-appendix-data">{data.join(" · ")}</p>}
        {event.importance && (
          <p className="story-appendix-bar">
            <strong>{event.importance.label}</strong> {event.importance.explanation}
          </p>
        )}
      </div>
    </>
  );
}
