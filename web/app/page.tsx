import Link from "next/link";
import { Typewriter, type TypewriterLine } from "@/components/landing/typewriter";
import evidence from "@/fixtures/landing/zetaris-evidence-russia-ukraine-war-2026-10-24.json";
import trace from "@/fixtures/landing/trace.sample.json";
import registry from "@/fixtures/landing/sources.json";
import rules from "@/fixtures/landing/rules.json";
import graph from "@/fixtures/landing/graph.json";
import "./landing.css";

// DECISION(2026-10-25, Anastasia/Claude Code): the landing is a server component that renders only
// committed fixtures (web/fixtures/landing) and copy; it calls no API, reads no database and shows
// no story text. Why: the public page must claim nothing the repository cannot back, and the web app
// never triggers paid work (docs/DECISIONS.md › Daily editions for users).
// DECISION(2026-10-26, Anastasia/Claude Code): the page is laid out as a wire service's front page
// (one grotesque, headlines at weight 500, metadata in monospace at 12 px, hairlines, square corners);
// the "blurred photo" of the brief is the day's own source tally blurred into tone (an inline SVG whose
// every text node is an "id count" pair of the evidence file, checked by web/tests/landing.cjs); the
// "puzzle" is the registry grid with its real gaps, split by the query each kind of source goes through.
// Why: Anastasia's second review (2026-10-26) and the design panel's verdict in web/DESIGN.md › Decisions.

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

function Kicker({ text, slug, href }: { text: string; slug: string; href: string }) {
  return (
    <p className="lp-kick">
      <span>{text}</span>
      <a href={href}>{slug}</a>
    </p>
  );
}

function TallyGroup({ title, sources, counts, caption }: { title: string; sources: Source[]; counts: Record<string, number>; caption: string }) {
  return (
    <div className="lp-tally-group">
      <h3>{title}</h3>
      <ol className="lp-tally" role="list">
        {sources.map((s) => {
          const n = counts[s.id];
          const noFeed = s.access_level_default === 3;
          return (
            <li key={s.id}>
              <span className="lp-tally-name">{s.name}</span>
              {n !== undefined ? (
                <span className="lp-tally-n">{n}</span>
              ) : (
                <span className="lp-tally-none">
                  <span aria-hidden="true">{noFeed ? "·" : "—"}</span>
                  <span className="lp-sr-only">{noFeed ? "no feed, access level 3" : "none matched"}</span>
                </span>
              )}
              <span className="lp-tally-meta">{[s.id, s.kind, s.flank, s.tier].filter(Boolean).join(" · ")}</span>
            </li>
          );
        })}
      </ol>
      <p className="lp-tally-cap">{caption}</p>
    </div>
  );
}

const STEPS: { n: string; title: string; who: string; body: string; loop?: string }[] = [
  { n: "01", title: "Plan and cluster", who: "model reads · code decides", body: "The day's documents are grouped into events. The model writes one structured key per document (actors, action, place, date); code buckets them by overlap and asks the model only about the pairs in between." },
  { n: "02", title: "Score the bar", who: "model reads · code decides", body: "The model reports the legal status and the state of the act; code maps them to points and decides above or below the bar. Ten stories a day is a cap, not a target." },
  { n: "03", title: "Extract claims", who: "model", body: "Atomic, checkable claims, each with the sentence it came from. A quote the code cannot find in the text is thrown out." },
  { n: "04", title: "Research ⇄ verify", who: "model reads · code decides", body: "Passages for and against each claim. A contradiction counts only when the model quotes it verbatim and code finds the words in the passage. A thin claim sends the event back for a second round.", loop: "research_rounds_max" },
  { n: "05", title: "Blind fact-check", who: "model", body: "A second agent, a different model, the same corpus and nothing from the first. If the two disagree, a third blind pass chooses between their evidence chains and code validates the answer. Still unresolved: disputed.", loop: "review_disputed_max" },
  { n: "06", title: "Write ⇄ critique", who: "model reads · code decides", body: "The article draft is checked against the writing rules. A rejected draft goes back to the writer. A third rejection is published flagged, never dropped and never quietly approved.", loop: "drafts_max" },
  { n: "07", title: "Roundup and publish", who: "model reads · code decides", body: "One line for every event below the bar, then one immutable snapshot per topic and day, with every trace row inside it." },
];

const GET: [string, string][] = [
  ["Home", "One card per topic you follow: the lead story and how many crossed the bar today, or “No story crossed the bar today”."],
  ["The story as an article", "Three to four minutes, built only from verified claims: what happened, what the parties say, what is not confirmed. Written by rules, no evaluation added."],
  ["Across the spectrum", "What left and right outlets highlighted, left out and how they worded it, by cohort, under the rating mode you pick: AllSides, MBFC, Ad Fontes or the average."],
  ["Also today", "One line for every event below the bar, with its source and status: confirmed, disputed, statements only, single source, unverified."],
];

const JOBS: [string, string][] = [
  ["Zetaris", "Every read of the corpus is SQL through Zetaris: sources, publications, official documents, previous days. The query above is one of them."],
  ["NVIDIA Nemotron", "Nemotron 3.5 Lightning reads, labels and writes. Nemotron 3 Ultra 550B is the blind fact-checker and the third reviewer."],
  ["Meterless", "Nightshift is supported as the primary provider, with an exact model id per lane and a signed receipt per call. The canonical runs so far used NVIDIA’s direct route; the Meterless engine integration is in progress."],
  ["Development", "Codex and Claude Code, an owner branch per block with stacked feature branches, every decision recorded in the repository next to the code it explains."],
];

export default function Home() {
  const f = figures();
  const reuters = supersedeChain(evidence.documents.sample.filter((s) => s.source_id === "reuters"));
  const chain: TypewriterLine[] = reuters.map((r) => ({ id: r.id, text: cut(r.title_80) }));
  const chainIds = reuters.map((r) => r.id).join(" → ");
  const docCounts = evidence.documents.by_source as Record<string, number>;
  const officialCounts = evidence.official_docs.by_source as Record<string, number>;
  const press = registry.sources.filter((s) => s.kind === "outlet" || s.kind === "agency");
  const bodies = registry.sources.filter((s) => s.kind === "official" || s.kind === "military");
  const matched = Object.keys(docCounts).length;
  const loops = rules.loops as Record<string, number>;
  const loopTargets = new Set(graph.loops.map((l) => l.to));

  return (
    <div className="landing">
      <header className="lp-head">
        <Link href="/" className="lp-masthead" aria-label="Quorum home">
          Quorum
        </Link>
        <nav className="lp-nav" aria-label="Sections">
          <a href="#get">What you get</a>
          <a href="#loop">Where it loops</a>
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
        <section className="lp-hero" aria-labelledby="hero-title">
          <p className="lp-wire">
            <span>{evidence.topic_id}</span>
            <span>{`Edition ${evidence.edition_date} · window ${windowLabel()}`}</span>
            <span>{`Run ${utc(evidence.run_at_utc)} · ${evidence.branch}@${evidence.commit}`}</span>
          </p>
          <div className="lp-hero-text">
            <p className="lp-eyebrow">
              <a href={HACKATHON}>Open Agent Hackathon 2026</a> · Track 03 · Reasoning Architecture
            </p>
            <h1 id="hero-title">The news, with its working shown.</h1>
            <p className="lp-lead">
              Quorum takes one event, reads how outlets across the spectrum and official bodies reported it,
              separates what is known from what is claimed, and shows you the evidence under every line.
            </p>
            <div className="lp-cta-row">
              <Link href="/register" className="lp-button">
                Choose your topics
              </Link>
              <a href="#loop" className="lp-button lp-button-quiet">
                See how one day is checked
              </a>
            </div>
          </div>
          <figure className="lp-chain">
            <Typewriter lines={chain} className="lp-type" />
            <figcaption>
              {`Three versions of one Reuters story, ${utc(reuters[0]?.published_at ?? evidence.run_at_utc)}, doc ${chainIds}. A re-edited publication is one publication: Quorum counts the chain once.`}
            </figcaption>
          </figure>
          <div className="lp-field-wrap" aria-hidden="true">
            <Field id="lp-blur-hero" />
          </div>
          <aside className="lp-sheet" aria-labelledby="evidence-title">
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
              <div>
                <dt>Left · right · agencies and unrated</dt>
                <dd>{`${f.left} · ${f.right} · ${f.unrated}`}</dd>
              </div>
              <div>
                <dt>Full text · headline and lead</dt>
                <dd>{`${f.fullText} · ${f.headlineOnly}`}</dd>
              </div>
              <div>
                <dt>Official documents</dt>
                <dd>{f.official}</dd>
              </div>
            </dl>
            <details className="lp-sql">
              <summary>Show the SQL</summary>
              <pre>
                <code>{evidence.sql.documents}</code>
              </pre>
              <pre>
                <code>{evidence.sql.official_docs}</code>
              </pre>
            </details>
            <dl className="lp-kv">
              <dt>Run</dt>
              <dd>{utc(evidence.run_at_utc)}</dd>
              <dt>Window</dt>
              <dd>{windowLabel()}</dd>
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
            <p className="lp-fine">No article text is stored or shown; titles are cut at 80 characters by the file.</p>
          </aside>
        </section>

        <section id="sources" className="lp-tally-section" aria-labelledby="tally-title">
          <Kicker text="By source · documents matched in the window" slug="collectors/sources.csv" href={`${REPO}/blob/master/collectors/sources.csv`} />
          <h2 id="tally-title">{`${registry.count} sources in the registry. ${matched} with documents in this window.`}</h2>
          <TallyGroup
            title="Outlets and agencies"
            sources={press}
            counts={docCounts}
            caption={`Rows in documents matched to ${evidence.topic_id} between ${windowLabel()}, by source. — none matched. · no feed (access level 3), never fetched.`}
          />
          <TallyGroup
            title="Official bodies and specialists"
            sources={bodies}
            counts={officialCounts}
            caption={`Queried separately, in official_docs: ${f.official} document in the window. — none matched.`}
          />
        </section>

        <section id="truth" className="lp-truth" aria-labelledby="truth-title">
          <h2 id="truth-title" className="lp-bracket">
            <span aria-hidden="true">(</span>What is truth?<span aria-hidden="true">)</span>
          </h2>
          <p className="lp-truth-answer">
            We believe a truth is a signed document, or a claim confirmed by sources that do not depend on each
            other. Everything else is a statement, and is shown as one.
          </p>
          <div className="lp-truth-cols">
            <p>
              A Democrat does not see the facts a Republican sees, or does not weigh them. A Republican, the other
              way round. Each gets one source and its interpretation.
            </p>
            <p>
              Quorum gives the fact first: what happened. Then, on request, how each outlet and each side told it,
              with the words they used.
            </p>
          </div>
        </section>

        <section id="get" className="lp-get" aria-labelledby="get-title">
          <Kicker text="What you get" slug="docs/DECISIONS.md › User account and interface" href={`${REPO}/blob/master/docs/DECISIONS.md`} />
          <h2 id="get-title">One card per topic. Then the article, then the appendix.</h2>
          <ol className="lp-rows" role="list">
            {GET.map(([title, body], i) => (
              <li key={title}>
                <span className="lp-row-n" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section id="loop" className="lp-loop" aria-labelledby="loop-title">
          <Kicker text="The graph · one run per topic per day" slug="docs/ARCHITECTURE.md § 5" href={`${REPO}/blob/master/docs/ARCHITECTURE.md`} />
          <h2 id="loop-title">Code decides. Models read. Every step leaves a row.</h2>
          <p className="lp-graph-line">
            {graph.nodes.map((n, i) => (
              <span key={n}>
                {i > 0 ? " → " : ""}
                <span className={loopTargets.has(n) ? "lp-graph-loop" : undefined}>{n}</span>
              </span>
            ))}
          </p>
          <ol className="lp-rows lp-steps" role="list">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="lp-row-n" aria-hidden="true">
                  {s.n}
                </span>
                <div>
                  <h3>
                    {s.title} <span className="lp-tag">{`[${s.who}]`}</span>
                  </h3>
                  <p>{s.body}</p>
                </div>
                {s.loop && <p className="lp-margin">{`↺ loops.${s.loop} = ${loops[s.loop]}`}</p>}
              </li>
            ))}
          </ol>
          <p className="lp-aside-note">
            An event that crosses the bar on points with no confirmed claim leaves the stories and goes to the
            roundup as “reported, not confirmed”.
          </p>
        </section>

        <section id="trace" className="lp-trace" aria-labelledby="trace-title">
          <Kicker text="The trace" slug="docs/examples/snapshot.sample.json" href={`${REPO}/blob/master/docs/examples/snapshot.sample.json`} />
          <h2 id="trace-title">Read the trace, not the summary.</h2>
          {trace.fictional && (
            <p className="lp-label">
              Dry run · fictional content · real shape. These rows come from the committed sample, not from a
              published edition.
            </p>
          )}
          <div className="lp-trace-table" role="table" aria-label="Trace rows">
            <div className="lp-trace-row lp-trace-head" role="row">
              <span role="columnheader">node</span>
              <span role="columnheader">decision</span>
              <span role="columnheader">reason</span>
            </div>
            {trace.rows.map((r, i) => (
              <div className="lp-trace-row" role="row" key={i}>
                <span role="cell">{r.iteration > 1 ? `${r.node} ·${r.iteration}` : r.node}</span>
                <span role="cell">{r.decision}</span>
                <span role="cell">{r.reason}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="runs" className="lp-sponsors" aria-labelledby="sponsors-title">
          <Kicker text="What runs where" slug="docs/DECISIONS.md › Stack and work blocks" href={`${REPO}/blob/master/docs/DECISIONS.md`} />
          <h2 id="sponsors-title">Each one does one job.</h2>
          <ol className="lp-rows" role="list">
            {JOBS.map(([title, body], i) => (
              <li key={title}>
                <span className="lp-row-n" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section id="limits" className="lp-limits" aria-labelledby="limits-title">
          <Kicker text="Limits" slug="reasoning/config/reasoning.toml" href={`${REPO}/blob/master/reasoning/config/reasoning.toml`} />
          <blockquote className="lp-quote">
            <p>“Comment is free, but facts are sacred.”</p>
            <cite>Manchester Guardian · 1921 · C. P. Scott</cite>
          </blockquote>
          <div className="lp-limits-grid">
            <div>
              <h2 id="limits-title">What it does not do.</h2>
              <ul className="lp-limits-list" role="list">
                <li>Forty sources in English, US outlets with three European agencies and papers. No social networks.</li>
                <li>Paywalled outlets count by headline and lead. A site that forbids our crawler counts the same way.</li>
                <li>
                  One edition per topic per day: the team runs it after the 05:30 New York cut and the deploy owner
                  installs it on the site; the site itself starts nothing. A topic outside the catalog is a request:
                  once the team adds it to collection, its first documents arrive within about an hour, and its page
                  says &ldquo;Waiting for its first brief&rdquo; until its first edition is installed.
                </li>
                <li>Positions on the spectrum come from AllSides, MBFC and Ad Fontes, not from us.</li>
                <li>No story on a quiet day. On 24 October 2026, the first real day, no event crossed the bar.</li>
                <li>
                  A signed-in reader today sees the catalog, the waiting state and a labelled fictional sample; real
                  editions appear behind the login once the judges&rsquo; edition reader is installed.
                </li>
              </ul>
            </div>
            <aside className="lp-forbidden" aria-labelledby="forbidden-title">
              <p id="forbidden-title" className="lp-eyebrow">
                Forbidden in a draft · reasoning.toml [writing]
              </p>
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
            </aside>
          </div>
        </section>

        <section id="team" className="lp-team" aria-labelledby="team-title">
          <Kicker text="Team Quorum" slug="github.com/rcc00n/Quorum" href={REPO} />
          <h2 id="team-title">Three people, one tracker.</h2>
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
          <p className="lp-fine">
            Built 22–27 October 2026 for the <a href={HACKATHON}>Open Agent Hackathon 2026</a>, Track 03. Decisions,
            code and the shared tracker are public: <a href={REPO}>github.com/rcc00n/Quorum</a>.
          </p>
        </section>

        <section id="final" className="lp-final" aria-labelledby="final-title">
          <div className="lp-field-wrap lp-field-wrap-final" aria-hidden="true">
            <Field id="lp-blur-final" />
          </div>
          <div className="lp-final-text">
            <h2 id="final-title">Choose your topics. Read the working.</h2>
            <Link href="/register" className="lp-button">
              Choose your topics
            </Link>
          </div>
        </section>
      </main>

      <footer className="lp-foot">
        <span className="lp-masthead lp-masthead-small">Quorum</span>
        <p>Evidence under every line.</p>
        <nav aria-label="Footer">
          <Link href="/login">Sign in</Link>
          <a href={REPO}>Repository</a>
          <a href={HACKATHON}>Hackathon</a>
        </nav>
      </footer>
    </div>
  );
}
