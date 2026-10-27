"use client";
import { Children, isValidElement, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import type { Event, Source } from "@/lib/api";
import { safeUrl } from "@/lib/api";
import { Story, StoryPhoto, storyReadable, ReviewLabel, formatDate } from "./story";
import { ImpactAssessment } from "./impact-assessment";
import { ChevronDown } from "lucide-react";

const views = [
  ["reading", "Read", "Reading", "The story, at your pace"],
  ["evidence", "Evidence", "Evidence", "Claims, sources and review decisions"],
  ["coverage", "Coverage", "Perspectives", "How outlets covered this event"],
  // DECISION(2026-10-27, Anastasia/Claude Code): the Map holds the sources used for this story (lib/story-sources.ts). Why: Anastasia, 2026-10-27.
  ["map", "Map", "Source map", "The sources used for this story"],
  ["trace", "Trace", "Investigation", "Recorded steps and revisions"],
  ["all", "All", "All sections", "The complete reading and investigation view"],
] as const;
type View = typeof views[number][0];
export function ReaderPanel({ children }: { name: Exclude<View, "all">; children: ReactNode }) { return <>{children}</>; }

// DECISION(2026-10-27, Anastasia/Claude Code; cabinet pages pass): the story's head (date, headline, review label, standfirst)
// sits above the view bar and scrolls away; the bar stays sticky as a tray of round pills without numbers or caption. Why:
// Anastasia's review of 2026-10-27, "the title on top, the menu under it, fixed while scrolling, rounded like Home".
export function InvestigationReader({ head, children, className = "" }: { title?: string; needsReview?: boolean; head?: ReactNode; children: ReactNode; className?: string }) {
  const [active, setActive] = useState<View>("reading");
  const [hashEpoch, setHashEpoch] = useState(0);
  const root = useRef<HTMLDivElement>(null), bar = useRef<HTMLElement>(null);
  const pendingTarget = useRef<HTMLElement | null>(null);
  const tabs = useRef(new Map<View, HTMLButtonElement>());
  const panels = Children.toArray(children).filter(isValidElement<{ name: Exclude<View, "all">; children: ReactNode }>);
  const pathname = usePathname(), search = useSearchParams()?.toString() ?? "";
  function resolveHash() {
    let id: string;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (!id) { setActive("reading"); return; }
    if (id === "reader-all") { setActive("all"); return; }
    const target = document.getElementById(id);
    const panel = target?.closest<HTMLElement>("[data-reader-panel]");
    if (!target || !panel || !root.current?.contains(panel)) return;
    pendingTarget.current = target;
    setHashEpoch(value => value + 1);
    setActive(panel.dataset.readerPanel as View);
  }
  useEffect(() => {
    resolveHash();
    window.addEventListener("hashchange", resolveHash); window.addEventListener("popstate", resolveHash);
    const header = document.querySelector<HTMLElement>(".sidebar");
    const resize = () => root.current?.style.setProperty("--reader-top", `${header?.getBoundingClientRect().height || 0}px`);
    resize(); const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    if (header) observer?.observe(header);
    return () => { window.removeEventListener("hashchange", resolveHash); window.removeEventListener("popstate", resolveHash); observer?.disconnect(); };
  }, []);
  // DECISION(2026-10-27, Anastasia/Claude Code): a router navigation that changes the path or the query (the app
  // search's "this story" items push `?date=…#reader-map`) fires neither hashchange nor popstate, so the hash is
  // resolved again whenever they change. Until the second cabinet pass the page blanked and the reader remounted on
  // every load, which read the hash by accident; a page that keeps its content while loading needs this instead.
  // Why: CI's navigator check (Enter on "Source map · this story") stayed on the previous view.
  useEffect(() => { resolveHash(); }, [pathname, search]); // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const target = pendingTarget.current; if (!target) return;
    // DECISION(2026-10-27, rcc00n/Codex): consume a deep link only after its pane is visible.
    // Why: hydration/hash events can change the pane before paint; focus must follow the committed visible DOM.
    if (active !== "all" && target.closest<HTMLElement>("[data-reader-panel]")?.dataset.readerPanel !== active) return;
    pendingTarget.current = null;
    for (let el: HTMLElement | null = target; el && el !== root.current; el = el.parentElement) if (el instanceof HTMLDetailsElement) el.open = true;
      const focus = target instanceof HTMLDetailsElement ? target.querySelector<HTMLElement>(":scope > summary") : target;
      if (focus) { if (!focus.hasAttribute("tabindex") && !focus.matches("a,button,input,select,summary")) focus.tabIndex = -1; focus.focus({ preventScroll: true }); }
    // A hash that names a pane itself (#reader-map from the app search, Back and Forward between views) starts at the
    // bar like a tab click; a deep link to something inside a pane keeps scrolling to it (review of 0c130c2).
    if (target.matches("[data-reader-panel]")) scrollToBar(); else target.scrollIntoView({ block: "start" });
  }, [active, hashEpoch]);
  // DECISION(2026-10-27, Anastasia/Claude Code): a chosen view starts at the bar, which then sits under the site
  // header, with the story's head scrolled away. Why: since the cabinet pages pass the head (date, headline, review
  // label, standfirst) sits inside the reader above the bar; scrolling to the reader's top left the whole head between
  // the header and the panel, and on the real 26 October edition the Source map's chart fell 14 px below the fold at
  // 390 px (master's installed-edition check, reader-checks.cjs). The head remains one scroll away. The bar is measured
  // where it sits in the flow (the content right under it, minus its height): a stuck bar reports where it is drawn,
  // under the header, so its own rectangle left the page where it was (review of 09fdb55).
  function scrollToBar() {
    const b = bar.current, content = b?.nextElementSibling;
    const top = b && content ? content.getBoundingClientRect().top + scrollY - b.offsetHeight
      : root.current ? root.current.getBoundingClientRect().top + scrollY : null;
    if (top === null) return;
    const header = document.querySelector<HTMLElement>(".sidebar")?.getBoundingClientRect().height || 0;
    window.scrollTo({ top: Math.max(0, top - header), behavior: "instant" });
  }
  // DECISION(2026-10-27, rcc00n/Codex; race traced by Anastasia/Claude Code): preserve Next's history state.
  // Why: its patched pushState otherwise re-syncs the router and may replace a subsequent claim hash with the old tab URL.
  function select(view: View) {
    pendingTarget.current = null; setActive(view);
    history.pushState(history.state, "", `#reader-${view}`);
    requestAnimationFrame(scrollToBar); // decision at scrollToBar
  }
  function navigate(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (e.key === "ArrowRight") next = (index + 1) % views.length;
    else if (e.key === "ArrowLeft") next = (index + views.length - 1) % views.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = views.length - 1;
    else return;
    e.preventDefault(); const view = views[next][0]; select(view); tabs.current.get(view)?.focus({ preventScroll: true });
  }
  return <div ref={root} className={`investigation-reader ${className}`} data-reader-view={active} onClickCapture={e => {
    const a = e.target instanceof Element ? e.target.closest<HTMLAnchorElement>('a[href^="#"]') : null;
    if (!a || active === "all") return;
    let target: HTMLElement | null; try { target = document.getElementById(decodeURIComponent(a.hash.slice(1))); } catch { return; }
    const panel = target?.closest<HTMLElement>("[data-reader-panel]");
    if (!target || !panel || !root.current?.contains(panel) || panel.dataset.readerPanel === active) return;
    e.preventDefault(); history.pushState(history.state, "", a.hash); pendingTarget.current = target; setActive(panel.dataset.readerPanel as View);
  }}>
    {head}
    <nav className="reader-bar" ref={bar} aria-label="Story workspace">
      <div role="tablist" aria-label="Story views" className="reader-tabs">
        {views.map(([id, label, name], i) => <button key={id} type="button" role="tab" id={`reader-tab-${id}`}
          aria-label={name} aria-selected={active === id} aria-controls={id === "all" ? "reader-content" : `reader-${id}`}
          tabIndex={active === id ? 0 : -1} onClick={() => select(id)} onKeyDown={e => navigate(e, i)}
          ref={el => { if (el) tabs.current.set(id, el); else tabs.current.delete(id); }}>{label}</button>)}
      </div>
    </nav>
    <div id="reader-content">{panels.map(panel => <div key={panel.props.name} id={`reader-${panel.props.name}`} data-reader-panel={panel.props.name}
      role="tabpanel" aria-labelledby={active === "all" ? "reader-tab-all" : `reader-tab-${panel.props.name}`} tabIndex={0}
      hidden={active !== "all" && active !== panel.props.name}>{panel.props.children}</div>)}</div>
  </div>;
}

export function LegacyClaims({ event }: { event: Event }) {
  // The five groups as rounded rows under one mono kicker, each with its count (cabinet pages pass, 2026-10-27):
  // the rows read as one list with a purpose instead of five unexplained links. Labels unchanged.
  return <div className="reader-brief"><p className="reader-brief-kicker">Claims and coverage</p>{(["established", "statements", "disputed", "unknown", "coverage"] as const).map((key, i) =>
    <details className="reader-brief-group" id={`claims-${key}`} key={key}>
      <summary>{["What is established", "Attributed statements", "Disputed claims", "What remains unknown", "Coverage differences"][i]}<span className="reader-brief-count">{event[key].length}</span><ChevronDown size={16} className="reader-brief-chevron" aria-hidden="true" /></summary>
      {event[key].length ? event[key].map((item, j) => <article key={j}><h3>{item.text}</h3><p>{item.explanation}</p>{item.sources.map((s, k) => safeUrl(s.url) && <a className="source-link" key={k} href={safeUrl(s.url)} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</article>) : <p className="muted">No information supplied for this section.</p>}
    </details>)}</div>;
}
export function EventReading({ event, sources, headless = false }: { event: Event; sources: Source[]; headless?: boolean }) {
  if (storyReadable(event, sources)) return <Story event={event} sources={sources} headless={headless} />;
  return <div className="reader-opening">{!headless && <><p className="eyebrow">EVENT ANALYSIS / {event.date}</p><h1>{event.title}</h1>
    {event.reasoning?.needs_review && <ReviewLabel />}<p className="lede">{event.summary}</p></>}
    {/* DECISION(2026-10-27, rcc00n/Codex): reviewed media is independent of the prose-readability gate.
        Why: a claims-only story still needs its image's caption/source/licence; claims and prose rules stay. */}
    {event.article?.photo && <div className="story-page"><StoryPhoto key={event.article.photo.url} photo={event.article.photo} /></div>}
    <ImpactAssessment event={event} />
    <LegacyClaims event={event} />
  </div>;
}
// The story's head above the view bar: the date in the mono, the headline in the display face, the review label when
// the producer flagged the story (words unchanged), the standfirst.
export function StoryHead({ event }: { event: Event }) {
  return <header className="reader-head">
    <p className="reader-head-date">{formatDate(event.date)}</p>
    <h1>{event.title}</h1>
    {event.reasoning?.needs_review && <ReviewLabel />}
    {event.summary && <p className="reader-head-lede">{event.summary}</p>}
  </header>;
}
