import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Typewriter } from "@/components/landing/typewriter";
import evidence from "@/fixtures/landing/zetaris-evidence-russia-ukraine-war-2026-10-24.json";
import trace from "@/fixtures/landing/trace.sample.json";
import "./landing.css";

// DECISION(2026-10-25, Anastasia/Claude Code): the landing is a server component that renders only
// committed fixtures (web/fixtures/landing) and copy; it calls no API, reads no database and shows
// no story text. Why: the public page must claim nothing the repository cannot back, and the web app
// never triggers paid work (docs/DECISIONS.md › Daily editions for users).

const REPO = "https://github.com/rcc00n/Quorum";
const HACKATHON = "https://hackathon.genai.works/event/open-agent-hackathon-2026";

type Flank = "left" | "right" | "None";

function evidenceFigures() {
  const docs = evidence.documents;
  const flank = docs.by_flank as Record<Flank, number>;
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
    runAt: evidence.run_at_utc,
    commit: evidence.commit,
    window: evidence.window_utc,
  };
}

function headlineChain() {
  // The three Reuters titles of one story, re-edited within a minute: a supersede chain.
  const reuters = evidence.documents.sample.filter((s) => s.source_id === "reuters");
  // The evidence file truncates titles to 80 characters; an ellipsis marks the cut, nothing is completed.
  return reuters.map((s) => (s.title_80.length >= 80 ? s.title_80 + "…" : s.title_80)).reverse();
}

function fmtUtc(iso: string) {
  const d = new Date(iso);
  return (
    d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }) +
    ", " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) +
    " UTC"
  );
}

const STEPS: { n: string; title: string; who: "model" | "code" | "both"; body: string; loop?: string }[] = [
  {
    n: "01",
    title: "Plan and cluster",
    who: "both",
    body: "The day's documents are grouped into events. The model writes one structured key per document (actors, action, place, date); code buckets them by overlap and asks the model only about the pairs in between.",
  },
  {
    n: "02",
    title: "Score the bar",
    who: "both",
    body: "The model reports the legal status and the state of the act; code maps them to points and decides above or below the bar. Ten stories a day is a cap, not a target.",
  },
  {
    n: "03",
    title: "Extract claims",
    who: "model",
    body: "Atomic, checkable claims, each with the sentence it came from. A quote the code cannot find in the text is thrown out.",
  },
  {
    n: "04",
    title: "Research ⇄ verify",
    who: "both",
    body: "Passages for and against each claim. A contradiction counts only when the model quotes it verbatim and code finds the words in the passage. A thin claim sends the event back for a second round.",
    loop: "at most two rounds",
  },
  {
    n: "05",
    title: "Blind fact-check",
    who: "model",
    body: "A second agent, a different model, the same corpus and nothing from the first. If the two disagree, a third blind pass chooses between their evidence chains and code validates the answer. Still unresolved: disputed.",
    loop: "one review per disagreement",
  },
  {
    n: "06",
    title: "Write ⇄ critique",
    who: "both",
    body: "The article draft is checked against the writing rules. A rejected draft goes back to the writer. A third rejection is published flagged, never dropped and never quietly approved.",
    loop: "at most three drafts",
  },
  {
    n: "07",
    title: "Roundup and publish",
    who: "both",
    body: "One line for every event below the bar, then one immutable snapshot per topic and day, with every trace row inside it.",
  },
];

export default function Home() {
  const f = evidenceFigures();
  const chain = headlineChain();
  const traceRows = trace.rows;
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
            Choose your topics <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      </header>

      <main id="main">
        <section className="lp-hero" aria-labelledby="hero-title">
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
                Choose your topics <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <a href="#loop" className="lp-button lp-button-quiet">
                See how one day is checked
              </a>
            </div>
            <figure className="lp-chain">
              <Typewriter lines={chain} className="lp-type" />
              <figcaption>
                One Reuters story, edited three times in one morning ({fmtUtc(evidence.documents.sample[0].published_at.replace(" ", "T") + "Z")}). Quorum counts it once.
              </figcaption>
            </figure>
          </div>

          <aside className="lp-card" aria-labelledby="evidence-title">
            <p className="lp-eyebrow">Real query · read through Zetaris</p>
            <h2 id="evidence-title" className="lp-card-title">
              {evidence.topic_id} · edition {evidence.edition_date}
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
                <dd>
                  <span className="lp-left">{f.left}</span> · <span className="lp-right">{f.right}</span> · {f.unrated}
                </dd>
              </div>
              <div>
                <dt>Full text · headline and lead</dt>
                <dd>
                  {f.fullText} · {f.headlineOnly}
                </dd>
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
            <p className="lp-fine">
              Run {fmtUtc(f.runAt)} over the collected corpus, window {f.window[0].slice(0, 16).replace("T", " ")}–
              {f.window[1].slice(0, 16).replace("T", " ")} UTC, data-collection@{f.commit}. No article text is stored or
              shown. File:{" "}
              <a href={`${REPO}/blob/master/collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json`}>
                collectors/zetaris/evidence
              </a>
              .
            </p>
          </aside>
        </section>

        <section className="lp-truth" aria-labelledby="truth-title">
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
          <p className="lp-eyebrow">What you get</p>
          <h2 id="get-title">One card per topic. Then the article, then the appendix.</h2>
          <ol className="lp-get-list">
            <li>
              <h3>Home</h3>
              <p>
                One card per topic you follow: the lead story and how many crossed the bar today, or “No story
                crossed the bar today”.
              </p>
            </li>
            <li>
              <h3>The story as an article</h3>
              <p>
                Three to four minutes, built only from verified claims: what happened, what the parties say, what is
                not confirmed. Written by rules, no evaluation added.
              </p>
            </li>
            <li>
              <h3>Across the spectrum</h3>
              <p>
                What left and right outlets highlighted, left out and how they worded it, by cohort, under the rating
                mode you pick: AllSides, MBFC, Ad Fontes or the average.
              </p>
            </li>
            <li>
              <h3>Also today</h3>
              <p>
                One line for every event below the bar, with its source and status: confirmed, disputed, statements
                only, single source, unverified.
              </p>
            </li>
          </ol>
        </section>

        <section id="loop" className="lp-loop" aria-labelledby="loop-title">
          <p className="lp-eyebrow">The graph · one run per topic per day</p>
          <h2 id="loop-title">Code decides. Models read. Every step leaves a row.</h2>
          <ol className="lp-steps">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="lp-step-n" aria-hidden="true">
                  {s.n}
                </span>
                <div>
                  <h3>
                    {s.title}{" "}
                    <span className={`lp-tag lp-tag-${s.who}`}>
                      {s.who === "both" ? "model reads · code decides" : s.who === "code" ? "code" : "model"}
                    </span>
                  </h3>
                  <p>{s.body}</p>
                  {s.loop && <p className="lp-loop-note">↺ {s.loop}</p>}
                </div>
              </li>
            ))}
          </ol>
          <p className="lp-aside-note">
            An event that crosses the bar on points with no confirmed claim leaves the stories and goes to the
            roundup as “reported, not confirmed”.
          </p>
        </section>

        <section className="lp-trace" aria-labelledby="trace-title">
          <p className="lp-eyebrow">The trace</p>
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
            {traceRows.map((r, i) => (
              <div className="lp-trace-row" role="row" key={i}>
                <span role="cell">
                  {r.node}
                  {r.iteration > 1 ? ` ·${r.iteration}` : ""}
                </span>
                <span role="cell">{r.decision}</span>
                <span role="cell">{r.reason}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-sponsors" aria-labelledby="sponsors-title">
          <p className="lp-eyebrow">What runs where</p>
          <h2 id="sponsors-title">Each one does one job.</h2>
          <dl className="lp-jobs">
            <div>
              <dt>Zetaris</dt>
              <dd>
                Every read of the corpus is SQL through Zetaris: sources, publications, official documents, previous
                days. The query above is one of them.
              </dd>
            </div>
            <div>
              <dt>NVIDIA Nemotron</dt>
              <dd>
                Nemotron 3.5 Lightning reads, labels and writes. Nemotron 3 Ultra 550B is the blind fact-checker and
                the third reviewer.
              </dd>
            </div>
            <div>
              <dt>Meterless</dt>
              <dd>
                Nightshift is supported as the primary provider, with an exact model id per lane and a signed receipt
                per call. The canonical runs so far used NVIDIA’s direct route; the Meterless engine integration is in
                progress.
              </dd>
            </div>
            <div>
              <dt>Development</dt>
              <dd>
                Codex and Claude Code, one branch per person, every decision recorded in the repository next to the
                code it explains.
              </dd>
            </div>
          </dl>
        </section>

        <section id="limits" className="lp-limits" aria-labelledby="limits-title">
          <blockquote className="lp-quote">
            <p>“Comment is free, but facts are sacred.”</p>
            <cite>C. P. Scott, Manchester Guardian, 1921</cite>
          </blockquote>
          <h2 id="limits-title">What it does not do.</h2>
          <ul className="lp-limits-list">
            <li>Forty US sources in English. No social networks.</li>
            <li>Paywalled outlets count by headline and lead. A site that forbids our crawler counts the same way.</li>
            <li>
              One edition per topic per day, prepared after the 05:30 New York cut by the team. A topic you add today
              has few documents until feeds accumulate, and the page says so.
            </li>
            <li>Positions on the spectrum come from AllSides, MBFC and Ad Fontes, not from us.</li>
            <li>No story on a quiet day. On 24 October 2026, the first real day, no event crossed the bar.</li>
            <li>What the preview shows today is a labelled fictional sample until the first real edition is published.</li>
          </ul>
        </section>

        <section id="team" className="lp-team" aria-labelledby="team-title">
          <p className="lp-eyebrow">Team Quorum</p>
          <h2 id="team-title">Three people, one tracker.</h2>
          <ul className="lp-team-list">
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

        <section className="lp-final" aria-labelledby="final-title">
          <h2 id="final-title">Choose your topics. Read the working.</h2>
          <Link href="/register" className="lp-button">
            Choose your topics <ArrowRight size={18} aria-hidden="true" />
          </Link>
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
