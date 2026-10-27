import { Fragment } from "react";
import { PageMotion } from "@/components/page-motion";
import Link from "next/link";
import { Tenets } from "@/components/landing/tenets";
import evidence from "@/fixtures/landing/zetaris-evidence-russia-ukraine-war-2026-10-24.json";
import trace from "@/fixtures/landing/trace.sample.json";
import registry from "@/fixtures/landing/sources.json";
import rules from "@/fixtures/landing/rules.json";
import graph from "@/fixtures/landing/graph.json";
import "./landing.css";
import "./landing-evidence.css";

// DECISION(2026-10-25, Anastasia/Claude Code): the landing is a server component that renders only
// committed fixtures (web/fixtures/landing) and copy; it calls no API, reads no database and shows
// no story text. Why: the public page must claim nothing the repository cannot back, and the web app
// never triggers paid work (docs/DECISIONS.md › Daily editions for users).
// DECISION(2026-10-26, Anastasia/Claude Code): the page is laid out as a wire service's front page
// (one grotesque, headlines at weight 500, metadata in monospace at 12 px, hairlines); the "blurred
// photo" of the brief is the day's own source tally blurred into tone (an inline SVG whose every text
// node is an "id count" pair of the evidence file, checked by web/tests/landing.cjs). Revised the same
// evening on Anastasia's review of the centred page: rounded corners, the sources as a spectrum, the
// article's anatomy, the graph as a timeline, the trace as a grouped ledger; see web/DESIGN.md › Decisions.
// Why: Anastasia's reviews of 2026-10-26 and the two design panels recorded in web/DESIGN.md › Decisions.

const REPO = "https://github.com/rcc00n/Quorum";
const HACKATHON = "https://hackathon.genai.works/event/open-agent-hackathon-2026";
const EVIDENCE_URL = `${REPO}/blob/master/collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json`;

type SampleRow = (typeof evidence.documents.sample)[number];
type Source = (typeof registry.sources)[number];

function figures() {
  const docs = evidence.documents;
  const flank = docs.by_flank as Record<string, number>;
  const access = docs.by_access_level as Record<string, number>;
  return {
    publications: docs.count,
    sources: Object.keys(docs.by_source).length,
    left: flank.left ?? 0,
    right: flank.right ?? 0,
    unrated: flank.None ?? 0,
    fullText: access["1"] ?? 0,
    headlineOnly: access["2"] ?? 0,
    official: evidence.official_docs.count,
  };
}

// The Reuters rows of the sample are one story re-edited: each row supersedes the previous one. The order
// comes from `supersedes_id`, never from the sample's order (which is newest first).
function supersedeChain(rows: SampleRow[]): SampleRow[] {
  const byId = new Map(rows.map((r) => [r.id, r]));
  let head = rows.find((r) => !r.supersedes_id || !byId.has(r.supersedes_id));
  const out: SampleRow[] = [];
  const seen = new Set<string>();
  while (head && !seen.has(head.id)) {
    out.push(head);
    seen.add(head.id);
    const current = head;
    head = rows.find((r) => r.supersedes_id === current.id);
  }
  return out;
}

// The running line's titles: the Reuters chain in supersede order first, then the other rows of the sample.
const wireTitles = (() => {
  const rows = evidence.documents.sample as SampleRow[];
  const ordered = supersedeChain(rows.filter((r) => r.source_id === "reuters"));
  return [...ordered, ...rows.filter((r) => !ordered.includes(r))];
})();

// The evidence file truncates titles to 80 characters; an ellipsis marks the cut, nothing is completed.
function cut(title: string) {
  return title.length >= 80 ? title + "…" : title;
}

function utc(iso: string) {
  const d = new Date(iso.replace(" ", "T").replace(/(\.\d+)?Z?$/, "Z"));
  const s = d.toISOString();
  return `${s.slice(0, 10)} ${s.slice(11, 19)} UTC`;
}

function windowLabel() {
  const [a, b] = evidence.window_utc;
  return `${a.slice(0, 10)} ${a.slice(11, 16)} – ${b.slice(0, 10)} ${b.slice(11, 16)} UTC`;
}

function dayLabel(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" });
}

// The blurred field: the tally of the window as letterforms softened into tone. Every text node is an
// "id count" pair of documents.by_source; the test reads them back from the served HTML.
function Field({ id }: { id: string }) {
  const pairs = Object.entries(evidence.documents.by_source).sort((a, b) => b[1] - a[1]);
  return (
    <svg className="lp-field" aria-hidden="true" focusable="false" viewBox="0 0 1200 720" preserveAspectRatio="xMaxYMin slice">
      <filter id={id} x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="22" />
      </filter>
      <g filter={`url(#${id})`} fontFamily='"Schibsted Grotesk Variable", system-ui, sans-serif' fontWeight={500} letterSpacing="-0.02em">
        {pairs.map(([source, count], i) => (
          <text
            key={source}
            x={20 + (i % 3) * 400}
            y={110 + Math.floor(i / 3) * 118}
            fontSize={i < 3 ? 120 : i < 9 ? 84 : 60}
            fill={i % 2 ? "#5f5a53" : "#7b5634"}
            fillOpacity={i % 2 ? 0.42 : 0.5}
          >
            {`${source} ${count}`}
          </text>
        ))}
      </g>
    </svg>
  );
}

function Kicker({ text, slug, href }: { text: string; slug?: string; href?: string }) {
  return (
    <p className="lp-kick">
      <span>{text}</span>
      {slug && href && <a href={href}>{slug}</a>}
    </p>
  );
}

/* The sources spectrum: the registry in three columns by flank, the day's counts as bar length. */
const docCounts = evidence.documents.by_source as Record<string, number>;
const officialCounts = evidence.official_docs.by_source as Record<string, number>;
const maxCount = Math.max(...Object.values(docCounts));
const maxSource = registry.sources.find((s) => docCounts[s.id] === maxCount);
const officialNames = registry.sources.filter((s) => officialCounts[s.id] !== undefined).map((s) => s.name);

type Column = "left" | "centre" | "right";
function columnOf(s: Source): Column {
  return s.flank === "left" ? "left" : s.flank === "right" ? "right" : "centre";
}
function countOf(s: Source): number | undefined {
  return docCounts[s.id] ?? officialCounts[s.id];
}
function accessWord(level: number) {
  return level === 1 ? "full text" : level === 2 ? "headline and lead" : "no feed";
}
function accessMark(level: number) {
  return level === 2 ? "headline" : level === 3 ? "no feed" : "";
}
// Count first (the day's loudest sources head each column), then major outlets, then registry order.
function sortRows(list: Source[]) {
  return [...list].sort(
    (a, b) =>
      (countOf(b) ?? 0) - (countOf(a) ?? 0) ||
      Number(b.tier === "major") - Number(a.tier === "major") ||
      registry.sources.indexOf(a) - registry.sources.indexOf(b),
  );
}
function barClass(s: Source, col: Column) {
  const tone = col === "centre" ? "ink" : `${col}-${s.tier === "major" ? "major" : "minor"}`;
  return `lp-src-bar lp-bar-${tone}${s.access_level_default === 2 ? " lp-bar-outline" : ""}`;
}

/* The seven steps of the graph. DECISION(2026-10-26, Anastasia/Claude Code): the vendor line per step names the
   lane and the code of docs/ARCHITECTURE.md § 5's node table and reasoning.toml [models] (default lane → Nemotron
   3.5 Lightning; fact_checker and reviewer → Nemotron 3 Ultra 550B); ● marks a node that calls a model, ○ a node
   that is code only; Meterless is named in #runs only, because the canonical runs used NVIDIA's direct route.
   Why: the page may not claim a route the journals do not back; if Yelysei changes a node's lane, only this
   constant changes. The nodes of the seven steps must cover graph.json in run order (checked below). */
type Step = { n: string; title: string; nodes: string[]; nodeLine: string; vendor: string; lead: string; body: string; loop?: keyof typeof rules.loops };
const STEPS: Step[] = [
  { n: "01", title: "Plan and cluster", nodes: ["plan", "cluster"], nodeLine: "○ plan · ● cluster", vendor: "Zetaris SQL · Nemotron 3.5 Lightning · merged in code", lead: "Groups the day's documents into events.", body: "The model writes one key per document: actors, action, place, date. Code merges the obvious pairs and asks the model only about the ones in between." },
  { n: "02", title: "Score the bar", nodes: ["score_importance"], nodeLine: "● score_importance", vendor: "Nemotron 3.5 Lightning · points by code", lead: "Decides what is big enough to be a story.", body: "The model reports the legal status and the state of the act; code turns them into points. Ten stories a day is a cap, not a target." },
  { n: "03", title: "Extract claims", nodes: ["extract_claims"], nodeLine: "● extract_claims", vendor: "Nemotron 3.5 Lightning · quotes checked by code", lead: "Breaks each event into checkable claims.", body: "Each claim keeps the sentence it came from. A quote code cannot find in the text is thrown out." },
  { n: "04", title: "Research and verify", nodes: ["research", "verify"], nodeLine: "● research ⇄ ○ verify", vendor: "Zetaris SQL · Nemotron 3.5 Lightning · verdict by rule", lead: "Looks for evidence for and against each claim.", body: "A contradiction counts only when the model quotes it and code finds the words in the passage. A thin claim sends the event back for a second round over the rest of the day, the official documents and earlier days.", loop: "research_rounds_max" },
  { n: "05", title: "Blind fact-check", nodes: ["fact_check", "adjudicate", "review_disputed", "escalate"], nodeLine: "● fact_check → ○ adjudicate ⇄ ● review_disputed → ○ escalate", vendor: "Nemotron 3 Ultra 550B · adjudicated in code", lead: "A second model checks again, seeing nothing from the first.", body: "Only events that can reach the bar get this check. Same corpus, no notes from the first pass. When the two disagree, a third blind pass chooses between their evidence chains and code validates the choice. Still unresolved: disputed.", loop: "review_disputed_max" },
  { n: "06", title: "Write and critique", nodes: ["frame", "write", "critique"], nodeLine: "● frame → ● write ⇄ ○ critique", vendor: "Nemotron 3.5 Lightning · rules checked in code", lead: "Writes the story, then checks it against the rules.", body: "A draft with a forbidden word or an unattributed statement goes back to the writer. A third rejection is published flagged, never dropped and never quietly approved.", loop: "drafts_max" },
  { n: "07", title: "Roundup and publish", nodes: ["roundup", "publish"], nodeLine: "● roundup · ● publish", vendor: "Nemotron 3.5 Lightning · one immutable snapshot", lead: "Everything else gets one line. Then one snapshot.", body: "One line per event below the bar, then one immutable snapshot per topic and day, with every trace row inside it." },
];
const stepNodes = STEPS.flatMap((s) => s.nodes);
if (stepNodes.length !== graph.nodes.length || graph.nodes.some((n, i) => stepNodes[i] !== n)) {
  throw new Error("landing: STEPS must cover graph.json's nodes in run order");
}
const STEP_OF_NODE: Record<string, string> = Object.fromEntries(STEPS.flatMap((s) => s.nodes.map((n) => [n, s.n])));
const GROUP_OF_NODE: Record<string, string> = {
  plan: "The day",
  cluster: "The day",
  score_importance: "The bar",
  extract_claims: "What is known",
  research: "What is known",
  verify: "What is known",
  fact_check: "What is known",
  adjudicate: "What is known",
  review_disputed: "What is known",
  escalate: "What is known",
  frame: "The story",
  write: "The story",
  critique: "The story",
  roundup: "Also today",
  publish: "The snapshot",
};
const loopByFrom = new Map(graph.loops.map((l) => [l.from, l]));
const loops = rules.loops as Record<string, number>;

const VENDORS: { name: string; where: string; text: string }[] = [
  { name: "Zetaris", where: "steps 01 · 04 · every read of the corpus", text: "Every read of the corpus is SQL through Zetaris: sources, publications, official documents, previous days. The query at the top of this page is one of them." },
  { name: "NVIDIA Nemotron", where: "3.5 Lightning · steps 01–04, 06, 07 · 3 Ultra 550B · step 05", text: "Nemotron 3.5 Lightning reads, labels and writes. Nemotron 3 Ultra 550B is the blind fact-checker and the third reviewer." },
  { name: "Meterless", where: "the provider lane · one model id per lane · a signed receipt per call", text: "Nightshift is supported as the primary provider, with an exact model id per lane and a signed receipt per call. The canonical runs so far used NVIDIA’s direct route; the Meterless engine integration is in progress." },
];

const LIMITS = [
  "Forty US sources in English. No social networks.",
  "Paywalled outlets count by headline and lead. A site that forbids our crawler counts the same way.",
  "One edition per topic per day, prepared by the team after the 05:30 New York cut. A topic you add today has few documents until feeds accumulate, and the page says so.",
  "Positions on the spectrum come from AllSides, MBFC and Ad Fontes, not from us.",
  "No story on a quiet day. On 24 October 2026, the first real day, no event crossed the bar.",
  "Until the first real edition, the preview shows a labelled fictional sample.",
];

/* The anatomy of a story: every slot is a rule of docs/DECISIONS.md › Stories as articles, not a sample text. */
type Part = { label: string; note?: string; kind: "home" | "headline" | "standfirst" | "key" | "facts" | "statements" | "open" | "appendix" | "also"; text: string };
const ANATOMY: Part[] = [
  { label: "Home", note: "One card per topic you follow.", kind: "home", text: "No story crossed the bar today." },
  { label: "Headline", kind: "headline", text: "Subject, verb, object. No adjectives." },
  { label: "Standfirst", kind: "standfirst", text: "Three facts." },
  { label: "Key", kind: "key", text: "Plain text is confirmed and links to its sources. “Says” is a statement. Not confirmed comes last." },
  { label: "Facts", note: "In the order they happened.", kind: "facts", text: "What happened, each sentence with its sources after it." },
  { label: "Statements", kind: "statements", text: "What the parties say, attributed in the sentence: “the White House says”." },
  { label: "Not confirmed", kind: "open", text: "What was reported but not confirmed, in one short paragraph at the end." },
  { label: "Appendix", note: "A reader who wants only the facts never reaches it.", kind: "appendix", text: "Across the spectrum: what left and right outlets highlighted, left out and how they worded it, under AllSides, MBFC, Ad Fontes or the average. Links to every claim and to the trace." },
  { label: "Also today", kind: "also", text: "One line for every event below the bar, with its source and status: confirmed, disputed, statements only, single source, unverified." },
];

export default function Home() {
  const f = figures();
  const columns: { key: Column; label: string; figure: number; line: string; rows: Source[] }[] = (["left", "centre", "right"] as Column[]).map((key) => {
    const members = registry.sources.filter((s) => columnOf(s) === key);
    const matched = members.filter((s) => docCounts[s.id] !== undefined).length;
    const flank = evidence.documents.by_flank as Record<string, number>;
    const label = key === "left" ? `Left · ${members.length} outlets` : key === "right" ? `Right · ${members.length} outlets` : `Centre and not rated · ${members.length}`;
    const figure = key === "left" ? flank.left ?? 0 : key === "right" ? flank.right ?? 0 : flank.None ?? 0;
    const line =
      key === "centre"
        ? `documents from ${matched} sources · ${f.official} official ${f.official === 1 ? "document" : "documents"}`
        : `documents from ${matched} sources`;
    return { key, label, figure, line, rows: sortRows(members) };
  });
  let lastGroup = "";

  return (
    <div className="landing">
      {/* The blurred field at the very back of the page (Anastasia, 2026-10-27): the window's tally as letterforms
          softened into tone, reaching from behind the header into the hero and the next section, edges faded by a
          mask so no border shows; every text node is an "id count" pair of documents.by_source and the test reads
          them back. */}
      <div className="lp-field-wrap" aria-hidden="true">
        <Field id="lp-blur-hero" />
      </div>
      <PageMotion root=".landing main" />
      <header className="lp-head">
        <Link href="/" className="lp-masthead" aria-label="Quorum home">
          Quorum
        </Link>
        <nav className="lp-nav" aria-label="Sections">
          <a href="#sources">Sources</a>
          <a href="#get">What you get</a>
          <a href="#loop">How it works</a>
          <a href="#limits">Limits</a>
          <a href="#team">Team</a>
        </nav>
        <div className="lp-actions">
          <Link href="/login" className="lp-link">
            Sign in
          </Link>
          <Link href="/register" className="lp-button">
            Choose your topics
          </Link>
        </div>
      </header>

      <main id="main">
        <section id="hero" className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-hero-text">
            <p className="lp-eyebrow">
              <a href={HACKATHON}>Open Agent Hackathon 2026</a> · Track 03 · Reasoning Architecture
            </p>
            <h1 id="hero-title">The news, with its working shown.</h1>
            <Tenets text={"Checked twice, by agents that never see each other\u2019s notes."} />
            <div className="lp-cta-row">
              <Link href="/register" className="lp-button">
                Choose your topics
              </Link>
              <a href="#loop" className="lp-button lp-button-quiet">
                See how a story is made
              </a>
            </div>
          </div>
          <aside className="lp-sheet lp-sheet-focus lp-sheet-compact" aria-labelledby="evidence-title">
            <p className="lp-eyebrow">Real query · read through Zetaris</p>
            <h2 id="evidence-title" className="lp-sheet-title">
              {`${evidence.topic_id} · edition ${evidence.edition_date}`}
            </h2>
            <dl className="lp-figures">
              <div>
                <dt>Publications</dt>
                <dd>{f.publications}</dd>
              </div>
              <div>
                <dt>Sources</dt>
                <dd>{f.sources}</dd>
              </div>
            </dl>
            {/* DECISION(2026-10-27, rcc00n/Codex): keep recorded counts/date/context visible and fold the intact query provenance.
                Why: Vadim requested readable emphasis; Anastasia approved this scope in Issue #2, with look review before merge. */}
            <details className="lp-sheet-details">
              <summary>Query details and provenance<span aria-hidden="true">+</span></summary>
              <dl className="lp-kv lp-kv-figures">
                <dt>Left · right · agencies and unrated</dt>
                <dd>{`${f.left} · ${f.right} · ${f.unrated}`}</dd>
                <dt>Full text · headline and lead</dt>
                <dd>{`${f.fullText} · ${f.headlineOnly}`}</dd>
                <dt>Official documents</dt>
                <dd>{f.official}</dd>
              </dl>
              <details className="lp-sql">
                <summary>Show the SQL</summary>
                <pre>
                  <code>{evidence.sql.documents}</code>
                </pre>
                <pre>
                  <code>{evidence.sql.official_docs}</code>
                </pre>
                <p className="lp-fine">No article text is stored or shown; titles are cut at 80 characters by the file.</p>
              </details>
              <dl className="lp-kv">
                <dt>Window</dt>
                <dd>{windowLabel()}</dd>
                <dt>Run</dt>
                <dd>{utc(evidence.run_at_utc)}</dd>
                <dt>Route</dt>
                <dd>{evidence.route}</dd>
                <dt>Datasource</dt>
                <dd>{evidence.datasource}</dd>
                <dt>Commit</dt>
                <dd>{`${evidence.branch}@${evidence.commit}`}</dd>
                <dt>File</dt>
                <dd>
                  <a href={EVIDENCE_URL}>collectors/zetaris/evidence</a>
                </dd>
              </dl>
            </details>
          </aside>
          {/* The deck's three running lines (web/DESIGN.md › Landing after the deck): the real titles of the window
              with their source tag, the chain's three Reuters rows first and in order (the test reads them back),
              then the registry, then the fifteen agents in run order. Each track holds its items twice for a
              seamless loop; the second half is hidden from assistive technology, and without motion the lines
              wrap and the duplicate is not shown. */}
          <div className="lp-wire" aria-label="Real headlines of the window, the forty sources and the fifteen agents">
            <div className="lp-line lp-line-big" style={{ "--d": "70s" } as React.CSSProperties}>
              <div className="lp-track">
                {[0, 1].map((half) => (
                  <Fragment key={half}>
                    {wireTitles.map((r) => (
                      <span key={`${half}-${r.id}`} aria-hidden={half === 1 ? true : undefined}>
                        <em>{r.source_id}</em>
                        {cut(r.title_80)}
                      </span>
                    ))}
                  </Fragment>
                ))}
              </div>
            </div>
            <div className="lp-line lp-line-reverse" style={{ "--d": "55s" } as React.CSSProperties}>
              <div className="lp-track">
                {[0, 1].map((half) => (
                  <Fragment key={half}>
                    {registry.sources.map((src) => (
                      <span key={`${half}-${src.id}`} aria-hidden={half === 1 ? true : undefined}>{src.name}</span>
                    ))}
                  </Fragment>
                ))}
              </div>
            </div>
            <div className="lp-line" style={{ "--d": "48s" } as React.CSSProperties}>
              <div className="lp-track">
                {[0, 1].map((half) => (
                  <Fragment key={half}>
                    {graph.nodes.map((n, i) => (
                      <span key={`${half}-${n}`} aria-hidden={half === 1 ? true : undefined}>{`${String(i + 1).padStart(2, "0")} · ${n}`}</span>
                    ))}
                  </Fragment>
                ))}
              </div>
            </div>
          </div>
          <p className="lp-wire-foot">
            {`Real titles read through Zetaris in the ${dayLabel(evidence.edition_date)} window, cut at 80 characters by the file · the ${registry.count} sources of the registry · the ${graph.nodes.length} agents in run order. Hover to pause.`}
          </p>
        </section>

        <section id="sources" className="lp-sources" aria-labelledby="sources-title">
          <Kicker text="Sources" slug="collectors/sources.csv" href={`${REPO}/blob/master/collectors/sources.csv`} />
          <h2 id="sources-title">Forty sources, left to right.</h2>
          <p className="lp-sub">{`Documents matched to ${evidence.topic_id} in the ${dayLabel(evidence.edition_date)} window, by source.`}</p>
          <div className="lp-spectrum">
            {columns.map((col) => (
              <div key={col.key} className={`lp-col lp-col-${col.key}`}>
                <div className="lp-col-head">
                  <span className="lp-col-label">{col.label}</span>
                  <span className="lp-col-figure">{col.figure}</span>
                  <span className="lp-col-line">{col.line}</span>
                </div>
                <ol className="lp-src-list" role="list" aria-label={col.label}>
                  {col.rows.map((s) => {
                    const n = countOf(s);
                    const level = s.access_level_default;
                    const mark = accessMark(level);
                    return (
                      <li key={s.id} className={n ? "lp-src" : "lp-src lp-src-quiet"}>
                        <span className="lp-src-name">
                          {s.name}
                          {mark && <span className="lp-src-access">{` ${mark}`}</span>}
                        </span>
                        {n !== undefined ? (
                          <span className="lp-src-n">{n}</span>
                        ) : (
                          <span className="lp-src-n lp-src-none">
                            <span aria-hidden="true">{level === 3 ? "·" : "—"}</span>
                            <span className="lp-sr-only">{level === 3 ? "no feed, access level 3" : "none matched"}</span>
                          </span>
                        )}
                        {n ? <span className={barClass(s, col.key)} style={{ width: `${(n / maxCount) * 100}%` }} aria-hidden="true" /> : null}
                      </li>
                    );
                  })}
                </ol>
              </div>
            ))}
          </div>
          <p className="lp-spectrum-legend">
            {`One scale, ${maxCount} = ${maxSource?.name ?? ""}. Solid: full text. Light fill with outline: headline and lead. — none matched. · no feed, never fetched.${officialNames.length ? ` ${officialNames.join(", ")}: counted in official_docs, queried separately.` : ""}`}
          </p>
          <details className="lp-registry">
            <summary>{`All ${registry.count} rows of the registry`}</summary>
            <ol role="list">
              {registry.sources.map((s) => (
                <li key={s.id}>{`${s.id} · ${s.kind}${s.flank ? " · " + s.flank : ""}${s.tier ? " · " + s.tier : ""} · ${accessWord(s.access_level_default)}`}</li>
              ))}
            </ol>
          </details>
        </section>

        <section id="truth" className="lp-truth" aria-labelledby="truth-title">
          <h2 id="truth-title" className="lp-bracket">
            <span aria-hidden="true">(</span>What is truth?<span aria-hidden="true">)</span>
          </h2>
          <p className="lp-truth-answer">
            A signed document, or a claim confirmed by sources that do not depend on each other. Everything else is
            a statement, and is shown as one.
          </p>
        </section>

        <section id="get" className="lp-get" aria-labelledby="get-title">
          <Kicker text="What you get" slug="docs/DECISIONS.md › Stories as articles" href={`${REPO}/blob/master/docs/DECISIONS.md#stories-as-articles`} />
          <h2 id="get-title">What you read each morning.</h2>
          <p className="lp-sub">One story per topic you follow. Two to four minutes, built only from verified claims, no evaluation added.</p>
          <div className="lp-page">
            {ANATOMY.map((part) => (
              <Fragment key={part.label}>
                <div className="lp-part">
                  <span className="lp-part-label">
                    <span className="lp-paren" aria-hidden="true">
                      {"( "}
                    </span>
                    {part.label}
                    <span className="lp-paren" aria-hidden="true">
                      {" )"}
                    </span>
                  </span>
                  {part.note && <span className="lp-part-note">{part.note}</span>}
                </div>
                <div className={`lp-slot lp-slot-${part.kind}`}>
                  {part.kind === "home" ? (
                    <div className="lp-home-card">
                      <span className="lp-card-meta">{`${evidence.topic_id} · edition ${evidence.edition_date}`}</span>
                      <span className="lp-home-line">{part.text}</span>
                    </div>
                  ) : part.kind === "standfirst" ? (
                    <p>
                      {part.text}
                      <span className="lp-slot-meta"> · 2–4 min</span>
                    </p>
                  ) : part.kind === "facts" ? (
                    <>
                      <p>{part.text}</p>
                      <span className="lp-slot-trail">evidence · source · quote · status</span>
                    </>
                  ) : part.kind === "also" ? (
                    <div className="lp-also-card">
                      <p>{part.text}</p>
                    </div>
                  ) : (
                    <p>{part.text}</p>
                  )}
                </div>
              </Fragment>
            ))}
          </div>
        </section>

        <section id="loop" className="lp-loop" aria-labelledby="loop-title">
          <Kicker text="How it works · one run per topic per day" slug="docs/ARCHITECTURE.md § 5" href={`${REPO}/blob/master/docs/ARCHITECTURE.md`} />
          <h2 id="loop-title">Seven steps from the feeds to the story.</h2>
          <p className="lp-sub">Models read and write. Code decides. Every step leaves a row in the trace.</p>
          <p className="lp-legend">{`${graph.nodes.length} nodes · ${graph.loops.length} loops · ● a model reads or writes · ○ code decides`}</p>
          <ol className="lp-steps" role="list">
            {STEPS.map((s) => (
              <li key={s.n} className={s.loop ? "lp-step lp-step-loop" : "lp-step"}>
                <div className="lp-step-label">
                  <span className="lp-step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p className="lp-step-nodes">{s.nodeLine}</p>
                  <p className="lp-step-vendor">{s.vendor}</p>
                  {s.loop && (
                    <span className="lp-chip">
                      <span className="lp-chip-mark" aria-hidden="true">
                        {"↺ "}
                      </span>
                      {`loops.${s.loop} = ${loops[s.loop]}`}
                    </span>
                  )}
                </div>
                <div className="lp-step-text">
                  <p className="lp-step-lead">{s.lead}</p>
                  <p className="lp-step-body">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="lp-card">
            <h3>No confirmed claim, no story.</h3>
            <p>
              An event that crosses the bar on points with no confirmed claim leaves the stories and goes to the
              roundup as “reported, not confirmed”.
            </p>
          </div>
        </section>

        <section id="trace" className="lp-trace" aria-labelledby="trace-title">
          <Kicker text="The trace" slug="docs/examples/snapshot.sample.json" href={`${REPO}/blob/master/docs/examples/snapshot.sample.json`} />
          <h2 id="trace-title">Under every story, its trace.</h2>
          <p className="lp-sub lp-sub-ink">
            These rows come from the committed dry-run sample, not from a published edition: a second research
            round and a rejected first draft are in them.
          </p>
          <div className="lp-ledger">
            <div className="lp-ledger-head">
              {trace.fictional && <span className="lp-ledger-label">Dry run · fictional content · real shape</span>}
              <span className="lp-ledger-count">{`${trace.rows.length} rows`}</span>
            </div>
            {trace.rows.map((r, i) => {
              const group = GROUP_OF_NODE[r.node] ?? "";
              const head = group !== lastGroup;
              lastGroup = group;
              // A loop row: the node is a loop's origin and its reason says "back to"; it gets an ink edge, no second
              // label, because the reason already names where the run went back to.
              const loops_back = loopByFrom.has(r.node) && /back to/.test(r.reason);
              return (
                <Fragment key={i}>
                  {head && <h3 className="lp-group-head">{group}</h3>}
                  <div className={loops_back ? "lp-ledger-row lp-ledger-loop" : "lp-ledger-row"}>
                    <span className="lp-ledger-step">{STEP_OF_NODE[r.node] ?? ""}</span>
                    <span className="lp-ledger-node">{r.iteration > 1 ? `${r.node} ·${r.iteration}` : r.node}</span>
                    <span className="lp-ledger-text">
                      <span className="lp-ledger-decision">{r.decision}</span>
                      <span className="lp-ledger-reason">{r.reason}</span>
                    </span>
                  </div>
                </Fragment>
              );
            })}
          </div>
        </section>

        <section id="runs" className="lp-sponsors" aria-labelledby="sponsors-title">
          <Kicker text="Sponsors" slug="docs/DECISIONS.md › Stack and work blocks" href={`${REPO}/blob/master/docs/DECISIONS.md#stack-and-work-blocks`} />
          <h2 id="sponsors-title">Each sponsor does one job.</h2>
          <ol className="lp-vendors" role="list">
            {VENDORS.map((v) => (
              <li key={v.name}>
                <div className="lp-vendor-cell">
                  <h3 className="lp-vendor-name">{v.name}</h3>
                  <p className="lp-vendor-where">{v.where}</p>
                </div>
                <p className="lp-vendor-text">{v.text}</p>
              </li>
            ))}
          </ol>
          <p className="lp-dev">
            Orchestration in LangGraph. Built with Codex and Claude Code, one branch per person, every decision
            recorded next to the code it explains.
          </p>
        </section>

        <section id="limits" className="lp-limits" aria-labelledby="limits-title">
          <Kicker text="Limits" slug="reasoning/config/reasoning.toml" href={`${REPO}/blob/master/reasoning/config/reasoning.toml`} />
          <h2 id="limits-title">What it does not do.</h2>
          <ul className="lp-limits-list" role="list">
            {LIMITS.map((text) => (
              <li key={text}>
                <span className="lp-dash" aria-hidden="true">
                  —
                </span>
                <p>{text}</p>
              </li>
            ))}
            <li>
              <span className="lp-dash" aria-hidden="true">
                —
              </span>
              <div>
                <p>{`${rules.forbidden_words.length} words a draft may not use.`}</p>
                <p className="lp-forbidden-words">
                  {rules.forbidden_words.map((w, i) => (
                    <span key={w}>
                      {i > 0 ? ", " : ""}
                      <s>{w}</s>
                    </span>
                  ))}
                  .
                </p>
                <p className="lp-forbidden-verbs">{`Attribution only as ${rules.attribution_verbs.join(", ")}.`}</p>
              </div>
            </li>
          </ul>
          <blockquote className="lp-quote">
            <p>“Comment is free, but facts are sacred.”</p>
            <cite>C. P. Scott · Manchester Guardian · 1921</cite>
          </blockquote>
        </section>

        <section id="team" className="lp-team" aria-labelledby="team-title">
          <Kicker text="Team" />
          <h2 id="team-title">Three people.</h2>
          <ul className="lp-team-list" role="list">
            <li>
              <strong>Yelysei Shkirpan</strong>
              <span>reasoning and the agent graph</span>
            </li>
            <li>
              <strong>Anastasia Shkirpan</strong>
              <span>data collection, portal look and experience</span>
            </li>
            <li>
              <strong>Vadim Rudenko</strong>
              <span>web platform, backend, deployment</span>
            </li>
          </ul>
        </section>

        <section id="final" className="lp-final" aria-labelledby="final-title">
          <h2 id="final-title">Read the working.</h2>
          <Link href="/register" className="lp-button">
            Choose your topics
          </Link>
          <Link href="/login" className="lp-link">
            Sign in
          </Link>
        </section>
      </main>

      <footer className="lp-foot">
        <span className="lp-masthead lp-masthead-small">Quorum</span>
        <p>Evidence under every line.</p>
        <nav aria-label="Footer">
          <a href={REPO}>github.com/rcc00n/Quorum</a>
          <Link href="/login">Sign in</Link>
        </nav>
      </footer>
    </div>
  );
}
