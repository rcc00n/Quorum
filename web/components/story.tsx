"use client";
import Link from "next/link";
import { ImpactAssessment } from "./impact-assessment";
import { Fragment, useState } from "react";
import type { Event, Source, Topic } from "@/lib/api";
import { rating, cohort, safeUrl } from "@/lib/api";
import type { Claim, StructuredAnalysis } from "@/lib/analysis";
import type { EditorialPhoto } from "@/lib/editorial";
import { licensedPhoto, readableArticle } from "@/lib/editorial";
import type { ReasoningStory } from "@/lib/reasoning";
import "@/app/story.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the story page (an event whose reasoning output supplied article
// paragraphs) is laid out as a printed page: the breadcrumb and the lead photo on the page column, every text
// element on a centred 560 px measure, the facts as plain text with their sources as small grey words after the
// paragraph, statements attributed inside the sentence, "Not confirmed." as the one run-in, a hairline, then the
// appendix head over the workspace's own sections. The page composes no prose: every string is a snapshot field,
// a counted number or one of the constants below (Yelysei's to approve). Why: Anastasia's brief of 2026-10-26
// (the prototype's indentation and ease of reading, in our identity), Yelysei's story-page specification and
// docs/DECISIONS.md › Stories as articles; the design panel's verdict is in web/DESIGN.md › Decisions.
// DECISION(2026-10-26, Anastasia/Claude Code; Vadim's and Yelysei's agreement given privately via Anastasia): the
// claims behind the article come from `event.analysis` when the portal supplied it, otherwise from the reasoning
// story under `event.reasoning` (the preview path, which by Vadim's rule invents no analysis). Claim keys and the
// evidence links exist only with an analysis; the reasoning path shows the sources' names and links alone. Why:
// the preview must show the writer's article without fabricating document ids, hashes or offsets.

const KEY_LINE =
  "Plain text is a confirmed fact with its sources after it. A statement is attributed in the sentence itself. What is not confirmed is listed at the end. No evaluation is added.";
const SAYS = "says";
const STATUS_WORDS: Record<string, string> = { disputed: "disputed", unknown: "unknown" };
const RUN_IN = "Not confirmed.";
const APPENDIX_KICKER = "Appendix";
const APPENDIX_TITLE = "Across the spectrum";
const APPENDIX_TAIL = " · Evidence and investigation";
const APPENDIX_SUB = "How the outlets told this story, every claim with its evidence, and the trace of the investigation.";
const CRUMB_FALLBACK = "Today";
// The lead slot when the edition carries no licensed photo (reasoning's photo tool is not built; every story
// arrives with photo: null). A blurred fill in the paper's colours and a plain sentence that says so.
const PHOTO_MISSING_LEAD = "Imagine a photo here.";
const PHOTO_MISSING_TAIL = "We ran out of hackathon before we got to this feature.";
// The spectrum body (Yelysei's story-page specification, 2026-10-26): his wording for the coverage sentence; the
// column labels, "Read as", "Example" and the two links are service lines for him to approve.
const SPECTRUM_SUB = "How outlets told this story, measured from their texts.";
const SIDE_WORDS = { left: "Left outlets", right: "Right outlets" } as const;
const SPECTRUM_LABELS = { highlights: "Leads with", omits: "Leaves out", wording: "Wording" } as const;
const EXAMPLE = "Example";
const READ_AS = "Read as";
const COHORT_WORDS: Record<string, string> = {
  major_left: "Big left outlets",
  minor_left: "Small left outlets",
  major_right: "Big right outlets",
  minor_right: "Small right outlets",
  center: "Centre outlets",
};
const CHECKED_LINK = "How this was checked";

type Paragraph = NonNullable<Event["article"]>["paragraphs"][number];
type Spectrum = ReasoningStory["spectrum"];
type Pair = [number, number];
type Mark = { kind: "word" | "source" | "key"; text: string; href?: string; title?: string; sep: boolean };
// One view of a claim, from either source of claims.
type ClaimView = {
  id: string;
  status: Claim["status"];
  speaker: string | null;
  text: string;
  supporting: { label: string; url: string; official: boolean; group: string }[];
};
type Claims = { byId: Map<string, ClaimView>; order: string[]; hasAnalysis: boolean };

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

// The Evidence Explorer's numbering, shared with its rows so the key in the text and the row carry one number.
export function claimKey(index: number) {
  return String(index + 1).padStart(2, "0");
}

export function formatDate(iso: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function claimsFromAnalysis(analysis: StructuredAnalysis, sources: Source[]): Claims {
  const byId = new Map<string, ClaimView>();
  analysis.claims.forEach((c) => {
    const supporting = c.supporting
      .map((citation) => analysis.documents.find((d) => d.id === citation.document_id))
      .filter((d): d is NonNullable<typeof d> => !!d)
      .map((d) => {
        const source = sources.find((s) => s.id === d.source_id);
        return {
          label: d.kind === "official" ? d.title : source?.name || d.title,
          url: d.url,
          official: d.kind === "official",
          group: d.kind === "official" ? `doc:${d.id}` : source?.independence_group || d.source_id,
        };
      });
    byId.set(c.id, { id: c.id, status: c.status, speaker: c.attribution?.speaker ?? null, text: c.text, supporting });
  });
  return { byId, order: analysis.claims.map((c) => c.id), hasAnalysis: true };
}

function claimsFromReasoning(story: ReasoningStory): Claims {
  const byId = new Map<string, ClaimView>();
  story.claims.forEach((c) => {
    const status: Claim["status"] =
      c.kind === "statement" ? "attributed" : c.status === "confirmed" ? "established" : c.status === "disputed" ? "disputed" : "unknown";
    const supporting = c.evidence
      .filter((e) => e.stance === "supports")
      .map((e) => ({
        label: e.title,
        url: e.url,
        official: !!e.is_document,
        group: e.is_document ? `doc:${e.url}` : e.independence_group || hostOf(e.url),
      }));
    byId.set(c.id, { id: c.id, status, speaker: c.speaker ?? null, text: c.text, supporting });
  });
  return { byId, order: story.claims.map((c) => c.id), hasAnalysis: false };
}

function claimsOf(event: Event, sources: Source[]): Claims | null {
  if (event.analysis) return claimsFromAnalysis(event.analysis, sources);
  if (event.reasoning) return claimsFromReasoning(event.reasoning);
  return null;
}

// Readable: with an analysis, lib/editorial's rule; with a reasoning story alone, the same rule over its claims
// (facts and context on established claims, statements on attributed claims with a speaker, the rest on
// unknown or disputed ones), in the fixed order facts → statements → not confirmed.
export function storyReadable(event: Event, sources: Source[]) {
  if (event.analysis) return readableArticle(event);
  const article = event.article;
  const claims = claimsOf(event, sources);
  if (!article?.paragraphs.length || !claims) return false;
  let previous = 0;
  return article.paragraphs.every((p) => {
    const order = p.kind === "statement" ? 1 : p.kind === "not_confirmed" ? 2 : 0;
    if (order < previous || !p.text.trim() || !p.claim_ids.length) return false;
    previous = order;
    return p.claim_ids.every((id) => {
      const c = claims.byId.get(id);
      return (
        !!c &&
        (order === 0 ? c.status === "established" : order === 1 ? c.status === "attributed" && !!c.speaker : ["unknown", "disputed"].includes(c.status))
      );
    });
  });
}

// Yelysei's rule (Issue #2 6418787032; ARCHITECTURE § 8): a story the producer flagged `needs_review` is shown
// with this label wherever its title appears, never silently approved.
export function ReviewLabel() {
  return (
    <p className="story-review" role="status">
      Requires editorial review
    </p>
  );
}

// DECISION(2026-10-27, Anastasia/Claude Code; second cabinet pass): the crumb leads back to where the reader came
// from. From Home (a client navigation from the board) it reads "Home" and steps back in history, so the board and
// its scroll return; otherwise, as before, it names the topic and leads to its page. Why: Anastasia's report of
// 2026-10-27: opening a story from Home and pressing the crumb landed on the topic page, not on Home.
export function StoryCrumb({ topic, date, fromHome = false }: { topic: Topic | null; date?: string; fromHome?: boolean }) {
  const href = fromHome
    ? `/dashboard${date ? `?date=${date}` : ""}`
    : topic ? `/topics/${encodeURIComponent(topic.id)}${date ? `?date=${date}` : ""}` : "/dashboard";
  return (
    <nav className="story-crumb" aria-label={fromHome ? "Home" : "Topic"}>
      <Link
        href={href}
        onClick={(e) => {
          if (fromHome && typeof history !== "undefined" && history.length > 1) {
            e.preventDefault();
            history.back();
          }
        }}
      >
        <span className="story-crumb-glyph" aria-hidden="true">
          ‹
        </span>
        {fromHome ? "Home" : topic ? topic.name : CRUMB_FALLBACK}
      </Link>
    </nav>
  );
}

// DECISION(2026-10-27, Anastasia/Claude Code): when no licensed photo exists the lead slot shows a blurred
// fill of the paper's own colours and one honest sentence, never a stock image or a fake photograph. The fill
// is decorative (aria-hidden); the sentence is plain text. Why: the photo tool did not fit in the hackathon,
// and an empty frame read as a bug; DECISIONS › Photos says no photo is fine, and a joke that says so plainly
// keeps the page honest.
function PhotoMissing() {
  return (
    <div className="story-photo story-photo-missing">
      <div className="story-photo-frame">
        <span className="story-photo-blur" aria-hidden="true" />
        <p className="story-photo-note">
          <span className="story-photo-note-lead">{PHOTO_MISSING_LEAD}</span> <span>{PHOTO_MISSING_TAIL}</span>
        </p>
      </div>
    </div>
  );
}

export function StoryPhoto({ photo }: { photo: EditorialPhoto }) {
  const [failed, setFailed] = useState(false);
  if (failed || !licensedPhoto(photo)) return <PhotoMissing />;
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
// claim keys when an analysis exists; after a not-confirmed paragraph only a status word and the key per claim,
// never an outlet.
function marksFor(p: Paragraph, claims: Claims): Mark[] {
  const views = p.claim_ids.map((id) => claims.byId.get(id)).filter((c): c is ClaimView => !!c);
  const marks: Mark[] = [];
  const keyFor = (c: ClaimView, sep: boolean): Mark | null => {
    if (!claims.hasAnalysis) return null;
    const index = claims.order.indexOf(c.id);
    return index < 0 ? null : { kind: "key", text: claimKey(index), href: `#claim-${encodeURIComponent(c.id)}`, title: c.text, sep };
  };
  if (p.kind === "not_confirmed") {
    views.forEach((c) => {
      marks.push({ kind: "word", text: STATUS_WORDS[c.status] ?? c.status, sep: marks.length > 0 });
      const key = keyFor(c, false);
      if (key) marks.push(key);
    });
    return marks;
  }
  if (p.kind === "statement") {
    const lower = p.text.toLowerCase();
    const speakers = [...new Set(views.map((c) => c.speaker).filter((s): s is string => !!s))];
    speakers.forEach((speaker) => {
      if (!lower.includes(speaker.toLowerCase())) marks.push({ kind: "word", text: `${speaker} ${SAYS}`, sep: marks.length > 0 });
    });
  }
  const docs = views.flatMap((c) => c.supporting);
  const ordered = [...docs.filter((d) => d.official), ...docs.filter((d) => !d.official)];
  const groups = new Set<string>();
  const labels = new Set<string>();
  ordered.forEach((d) => {
    if (groups.has(d.group)) return;
    groups.add(d.group);
    if (labels.has(d.label)) return;
    labels.add(d.label);
    const href = safeUrl(d.url);
    marks.push({ kind: href ? "source" : "word", text: d.label, href, title: d.official ? d.label : undefined, sep: marks.length > 0 });
  });
  let first = true;
  views.forEach((c) => {
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
function metaSegments(article: NonNullable<Event["article"]>, claims: Claims) {
  const ids = (kinds: string[]) => new Set(article.paragraphs.filter((p) => kinds.includes(p.kind)).flatMap((p) => p.claim_ids));
  const facts = ids(["fact", "context"]).size;
  const statements = ids(["statement"]).size;
  const open = [...ids(["not_confirmed"])].map((id) => claims.byId.get(id)?.status);
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

// Coverage in Yelysei's words: big = major left + major right, small = minor left + minor right, each a pair
// [covered, total] of spectrum.coverage; a cohort with a total and no coverage is named as silent.
function coveragePairs(spectrum: Spectrum) {
  const pair = (key: string): Pair => (spectrum.coverage as Record<string, Pair | undefined>)[key] ?? [0, 0];
  const sum = (a: Pair, b: Pair): Pair => [a[0] + b[0], a[1] + b[1]];
  return { big: sum(pair("major_left"), pair("major_right")), small: sum(pair("minor_left"), pair("minor_right")), centre: pair("center") };
}
function coverageLine(spectrum: Spectrum) {
  const { big, small, centre } = coveragePairs(spectrum);
  const part = ([c, t]: Pair, word: string) => (t ? (c === t ? `all ${t} ${word}` : `${c} of ${t} ${word}`) : null);
  const parts = [part(big, "big outlets"), part(small, "small ones"), part(centre, "centre outlets")].filter((p): p is string => !!p);
  return parts.length ? `Covered by ${parts.join(" and ")}, by the ${spectrum.rating_mode} rating.` : null;
}
function silenceLines(spectrum: Spectrum) {
  return Object.entries(spectrum.coverage as Record<string, Pair | undefined>)
    .filter(([, v]) => v && v[1] > 0 && v[0] === 0)
    .map(([key]) => `${COHORT_WORDS[key] ?? key} did not cover this story.`);
}
function interpretationsLine(spectrum: Spectrum) {
  const items = (spectrum.interpretations ?? []).filter((i) => i.label);
  return items.length ? items.map((i) => `${i.label} — ${plural(i.outlets, "outlet", "outlets")}, mostly ${i.mostly}`).join(" · ") : null;
}

function SpectrumSide({ side, data }: { side: "left" | "right"; data: NonNullable<Spectrum["left"]> }) {
  const rows = (["highlights", "omits", "wording"] as const).filter((k) => data[k]?.trim());
  const example = safeUrl(data.example_url);
  if (!rows.length && !example) return null;
  return (
    <div className="story-spectrum-side">
      <h3>{SIDE_WORDS[side]}</h3>
      <dl>
        {rows.map((k) => (
          <Fragment key={k}>
            <dt>{SPECTRUM_LABELS[k]}</dt>
            <dd>{k === "wording" ? `“${data[k]}”` : data[k]}</dd>
          </Fragment>
        ))}
      </dl>
      {example && (
        <a className="story-spectrum-example" href={example} target="_blank" rel="noopener noreferrer">
          {EXAMPLE}
        </a>
      )}
    </div>
  );
}

function runIn(text: string): [string | null, string] {
  const m = text.match(/^(not confirmed[.:])\s*/i);
  return m ? [m[1], text.slice(m[0].length)] : [null, text];
}

export function Story({ event, sources, headless = false }: { event: Event; sources: Source[]; headless?: boolean }) {
  const claims = claimsOf(event, sources);
  if (!claims || !storyReadable(event, sources)) return null;
  const article = event.article!;
  const analysis = event.analysis;
  const meta = metaSegments(article, claims);
  const data = analysis ? dataSegments(analysis, sources) : [];
  const silence = analysis ? silentCohorts(analysis, sources) : [];
  const spectrum = event.reasoning?.spectrum;
  const coverage = spectrum ? coverageLine(spectrum) : null;
  const spectrumSilence = spectrum ? silenceLines(spectrum) : [];
  const readAs = spectrum ? interpretationsLine(spectrum) : null;
  const sides = spectrum ? (["left", "right"] as const).filter((s) => spectrum[s]) : [];
  const claimsHref = claims.hasAnalysis ? "#evidence-explorer" : "#claims-established";
  let runInUsed = false;
  return (
    <>
      <article className="story" aria-label="Source-backed article">
        {article.photo ? <StoryPhoto key={article.photo.url} photo={article.photo} /> : <PhotoMissing />}
        {/* In the reader the date, headline, standfirst and review label are the head above the view bar
            (components/investigation-reader.tsx StoryHead); the article keeps its photo, meta and body. */}
        {!headless && (
          <>
            <time className="story-date" dateTime={event.date}>
              {formatDate(event.date)}
            </time>
            <h1 className="story-headline">{event.title}</h1>
            <p className="story-standfirst">{event.summary}</p>
          </>
        )}
        {meta.length > 0 && <p className="story-meta">{meta.join(" · ")}</p>}
        {!headless && event.reasoning?.needs_review && <ReviewLabel />}
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
              <Marks marks={marksFor(p, claims)} />
            </p>
          );
        })}
        {silence.map((line) => (
          <p className="story-silence" key={line}>
            {line}
          </p>
        ))}
      </article>
      <div className="story-appendix">
        <p className="story-appendix-kicker">{APPENDIX_KICKER}</p>
        <h2 className="story-appendix-title">
          {APPENDIX_TITLE}
          <span className="story-appendix-tail">{APPENDIX_TAIL}</span>
        </h2>
        <p className="story-appendix-sub">{spectrum ? `${SPECTRUM_SUB}${coverage ? ` ${coverage}` : ""}` : APPENDIX_SUB}</p>
        {!spectrum && data.length > 0 && <p className="story-appendix-data">{data.join(" · ")}</p>}
        {sides.length > 0 && (
          <div className={sides.length === 2 ? "story-spectrum" : "story-spectrum story-spectrum-one"}>
            {sides.map((s) => (
              <SpectrumSide key={s} side={s} data={spectrum![s]!} />
            ))}
          </div>
        )}
        {readAs && <p className="story-appendix-read">{`${READ_AS}: ${readAs}.`}</p>}
        {spectrum?.note?.trim() && <p className="story-appendix-note">{spectrum.note}</p>}
        {spectrumSilence.map((line) => (
          <p className="story-appendix-silence" key={line}>
            {line}
          </p>
        ))}
        {event.importance && <ImpactAssessment event={event} />}
        <p className="story-appendix-links">
          <a href={claimsHref}>{`All ${plural(claims.order.length, "claim", "claims")} with evidence`}</a>
          {claims.hasAnalysis && <a href="#investigation-timeline">{CHECKED_LINK}</a>}
        </p>
      </div>
    </>
  );
}
