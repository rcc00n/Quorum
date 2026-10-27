"use client";
import { Children, isValidElement, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import type { Event, Source } from "@/lib/api";
import { safeUrl } from "@/lib/api";
import { Story, storyReadable, ReviewLabel } from "./story";

const views = [
  ["reading", "Read", "Reading", "The story, at your pace"],
  ["evidence", "Evidence", "Evidence", "Claims, sources and review decisions"],
  ["coverage", "Coverage", "Perspectives", "How outlets covered this event"],
  ["map", "Map", "Source map", "Registry ratings and cited audience"],
  ["trace", "Trace", "Investigation", "Recorded steps and revisions"],
  ["all", "All", "All sections", "The complete reading and investigation view"],
] as const;
type View = typeof views[number][0];
export function ReaderPanel({ children }: { name: Exclude<View, "all">; children: ReactNode }) { return <>{children}</>; }

export function InvestigationReader({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  const [active, setActive] = useState<View>("reading");
  const root = useRef<HTMLDivElement>(null), bar = useRef<HTMLElement>(null);
  const pendingTarget = useRef<HTMLElement | null>(null);
  const tabs = useRef(new Map<View, HTMLButtonElement>());
  const panels = Children.toArray(children).filter(isValidElement<{ name: Exclude<View, "all">; children: ReactNode }>);
  function resolveHash() {
    let id: string;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (!id) { setActive("reading"); return; }
    if (id === "reader-all") { setActive("all"); return; }
    const target = document.getElementById(id);
    const panel = target?.closest<HTMLElement>("[data-reader-panel]");
    if (!target || !panel || !root.current?.contains(panel)) return;
    pendingTarget.current = target;
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
  useEffect(() => {
    const target = pendingTarget.current; if (!target) return;
    pendingTarget.current = null;
    const frame = requestAnimationFrame(() => {
      for (let el: HTMLElement | null = target; el && el !== root.current; el = el.parentElement) if (el instanceof HTMLDetailsElement) el.open = true;
      const focus = target instanceof HTMLDetailsElement ? target.querySelector<HTMLElement>(":scope > summary") : target;
      if (focus) { if (!focus.hasAttribute("tabindex") && !focus.matches("a,button,input,select,summary")) focus.tabIndex = -1; focus.focus({ preventScroll: true }); }
      target.scrollIntoView({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);
  function select(view: View) {
    pendingTarget.current = null; setActive(view);
    history.pushState(null, "", `#reader-${view}`);
    requestAnimationFrame(() => {
      const el = root.current; if (!el) return;
      const header = document.querySelector<HTMLElement>(".sidebar")?.getBoundingClientRect().height || 0;
      window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - header), behavior: "instant" });
    });
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
    e.preventDefault(); history.pushState(null, "", a.hash); pendingTarget.current = target; setActive(panel.dataset.readerPanel as View);
  }}>
    <nav className="reader-bar" ref={bar} aria-label="Story workspace">
      <div className="reader-bar-caption"><span>Read. Compare. Verify.</span><span>{views.find(v => v[0] === active)?.[3]}</span></div>
      <div role="tablist" aria-label="Story views" className="reader-tabs">
        {views.map(([id, label, name], i) => <button key={id} type="button" role="tab" id={`reader-tab-${id}`}
          aria-label={name} aria-selected={active === id} aria-controls={id === "all" ? "reader-content" : `reader-${id}`}
          tabIndex={active === id ? 0 : -1} onClick={() => select(id)} onKeyDown={e => navigate(e, i)}
          ref={el => { if (el) tabs.current.set(id, el); else tabs.current.delete(id); }}><span className="reader-tab-number">0{i + 1}</span>{label}</button>)}
      </div>
    </nav>
    {active !== "reading" && active !== "all" && <h1 className="reader-story-context">{title}</h1>}
    <div id="reader-content">{panels.map(panel => <div key={panel.props.name} id={`reader-${panel.props.name}`} data-reader-panel={panel.props.name}
      role="tabpanel" aria-labelledby={active === "all" ? "reader-tab-all" : `reader-tab-${panel.props.name}`} tabIndex={0}
      hidden={active !== "all" && active !== panel.props.name}>{panel.props.children}</div>)}</div>
  </div>;
}

export function LegacyClaims({ event }: { event: Event }) {
  return <div className="reader-brief">{(["established", "statements", "disputed", "unknown", "coverage"] as const).map((key, i) =>
    <details className="reader-brief-group" id={`claims-${key}`} key={key}>
      <summary>{["What is established", "Attributed statements", "Disputed claims", "What remains unknown", "Coverage differences"][i]}<span aria-hidden="true">↗</span></summary>
      {event[key].length ? event[key].map((item, j) => <article key={j}><h3>{item.text}</h3><p>{item.explanation}</p>{item.sources.map((s, k) => safeUrl(s.url) && <a className="source-link" key={k} href={safeUrl(s.url)} target="_blank" rel="noopener noreferrer">{s.title} ↗</a>)}</article>) : <p className="muted">No information supplied for this section.</p>}
    </details>)}</div>;
}
export function EventReading({ event, sources }: { event: Event; sources: Source[] }) {
  if (storyReadable(event, sources)) return <Story event={event} sources={sources} />;
  return <div className="reader-opening"><p className="eyebrow">EVENT ANALYSIS / {event.date}</p><h1>{event.title}</h1>
    {event.reasoning?.needs_review && <ReviewLabel />}<p className="lede">{event.summary}</p>
    {event.importance && <aside className="notice"><strong>{event.importance.label}</strong><p>{event.importance.explanation}</p></aside>}
    <LegacyClaims event={event} />
  </div>;
}
