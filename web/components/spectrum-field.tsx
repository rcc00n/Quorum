"use client";
import { useEffect, useRef } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";
import type { Source } from "@/lib/api";
import { cohort, rating, safeUrl } from "@/lib/api";
import { spectrumGeometry } from "@/lib/spectrum-geometry";
import { usedLabel } from "@/lib/story-sources";
import type { SpectrumScope } from "@/lib/story-sources";

const compact = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
// DECISION(2026-10-27, Anastasia/Claude Code; WEB-SPECTRUM-POLISH-02, Vadim's scope): every plotted mark carries a
// label from the registry's own identity, never a typed list: a major-tier source (registry `tier`) wears its `id`
// as a short badge (upper case, hyphens as spaces), always visible from 701 px; every other source shows its `name`
// on hover, keyboard focus and selection. Labels anchor away from the plot's edges by the mark's x, and two
// major badges that would collide stack the smaller audience below its mark. On phones badges show only on the
// selected mark. Labels are aria-hidden: the button's aria-label already names the source. Why: Anastasia's
// review of the spectrum (Issue #2, 2026-10-27): an unlabelled field cannot be read without the inspector.
export function markLabel(source: Pick<Source, "id" | "name" | "tier">) {
  return source.tier === "major" ? source.id.toUpperCase().replace(/-/g, " ") : source.name;
}
export function labelLayout(points: { id: string; x: number; y: number; audience: number }[], major: Set<string>) {
  const placed: { x: number; y: number; pos: "above" | "below" }[] = [];
  const layout = new Map<string, { side: "left" | "right" | "center"; pos: "above" | "below" }>();
  for (const p of [...points].filter(p => major.has(p.id)).sort((a, b) => b.audience - a.audience)) {
    const collides = placed.some(q => Math.abs(q.x - p.x) < 7 && Math.abs(q.y - p.y) < 9 && q.pos === "above")
      || points.some(q => q.id !== p.id && Math.abs(q.x - p.x) < 4 && p.y - q.y > 3 && p.y - q.y < 12); // a mark right above
    const pos = collides ? "below" : "above";
    placed.push({ x: p.x, y: p.y, pos });
    layout.set(p.id, { side: p.x >= 80 ? "right" : p.x <= 20 ? "left" : "center", pos });
  }
  for (const p of points) if (!layout.has(p.id)) layout.set(p.id, { side: p.x >= 80 ? "right" : p.x <= 20 ? "left" : "center", pos: "above" });
  return layout;
}
export function SpectrumField({ sources, mode, selectedId, onSelect, scope = "registry" }: {
  sources: Source[]; mode: string; selectedId: string | null; onSelect: (id: string) => void; scope?: SpectrumScope;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const plane = useRef<HTMLDivElement>(null);
  const pending = useRef(0);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const rated = sources.filter(s => rating(s, mode) !== null);
  const geometry = spectrumGeometry(sources.flatMap(s => {
    const score = rating(s, mode);
    return score !== null && s.audience !== null && safeUrl(s.audience_source_url || "")
      ? [{ id: s.id, score, audience: s.audience }] : [];
  }));
  const selected = sources.find(s => s.id === selectedId) || sources.find(s => s.id === geometry.points[0]?.id) || sources[0];
  const active = geometry.points.find(p => p.id === selected?.id);
  const focusId = active?.id || geometry.points[0]?.id;
  const majorIds = new Set(sources.filter(s => s.tier === "major").map(s => s.id));
  const labels = labelLayout(geometry.points, majorIds);
  const score = selected ? rating(selected, mode) : null;
  const audienceUrl = selected ? safeUrl(selected.audience_source_url || "") : undefined;

  useEffect(() => {
    const el = frame.current;
    if (!el || !window.IntersectionObserver) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) { el.dataset.entered = "true"; observer.disconnect(); }
    }, { threshold: .15 });
    observer.observe(el);
    return () => { observer.disconnect(); if (pending.current) cancelAnimationFrame(pending.current); };
  }, []);
  function tilt(e: PointerEvent<HTMLDivElement>) {
    if (!window.matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)").matches || pending.current) return;
    const { clientX, clientY } = e;
    pending.current = requestAnimationFrame(() => {
      pending.current = 0;
      const el = plane.current; if (!el) return;
      const box = el.getBoundingClientRect();
      el.style.setProperty("--sp-ry", `${((clientX - box.left) / box.width - .5) * 3}deg`);
      el.style.setProperty("--sp-rx", `${((clientY - box.top) / box.height - .5) * -2}deg`);
    });
  }
  function reset() {
    if (pending.current) cancelAnimationFrame(pending.current);
    pending.current = 0;
    plane.current?.style.setProperty("--sp-ry", "0deg");
    plane.current?.style.setProperty("--sp-rx", "0deg");
  }
  function navigate(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (index + 1) % geometry.points.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (index + geometry.points.length - 1) % geometry.points.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = geometry.points.length - 1;
    else return;
    e.preventDefault();
    const point = geometry.points[next]; onSelect(point.id); buttons.current.get(point.id)?.focus();
  }
  return (
    <div className="spectrum-instrument" ref={frame}>
      <div className="sp-caption">
        <span>Source position × audience</span>
        <span>{geometry.points.length} plotted · {rated.length} rated · {sources.length} {scope === "story" ? "used for this story" : "in registry"}</span>
      </div>
      {geometry.points.length ? <>
        <p className="sp-instruction">Select a source to inspect its ratings. Arrow keys move between plotted sources.</p>
        <div className="sp-stage" ref={plane} onPointerMove={tilt} onPointerLeave={reset}>
          <div className="sp-y-label">Audience · log scale</div>
          <div className="sp-chart">
            {geometry.ticks.map((tick, i) => <span className="sp-y-tick" style={{ top: `${tick.y}%` }} key={i}>{compact(tick.audience)}</span>)}
            <svg className="sp-grid" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <rect x="0" y="0" width="37.5" height="100" className="sp-zone-left" />
              <rect x="62.5" y="0" width="37.5" height="100" className="sp-zone-right" />
              {[0, 25, 50, 75, 100].map(y => <line key={`h${y}`} x1="0" x2="100" y1={y} y2={y} />)}
              {[0, 25, 50, 75, 100].map(x => <line key={`v${x}`} x1={x} x2={x} y1="0" y2="100" />)}
              {[37.5, 62.5].map(x => <line key={x} x1={x} x2={x} y1="0" y2="100" className="sp-boundary" />)}
              {active && <g className="sp-crosshair"><line x1={active.x} x2={active.x} y1={active.y} y2="100" /><line x1="0" x2={active.x} y1={active.y} y2={active.y} /></g>}
            </svg>
            {geometry.points.map((p, i) => {
              const source = sources.find(s => s.id === p.id)!;
              const lean = cohort(p.score).toLowerCase();
              const label = labels.get(p.id)!;
              return <button type="button" className={`sp-point sp-point-${lean}${majorIds.has(p.id) ? " sp-point-major" : ""}`} key={p.id}
                ref={node => { if (node) buttons.current.set(p.id, node); else buttons.current.delete(p.id); }}
                style={{ left: `${p.x}%`, top: `${p.y}%`, "--sp-delay": `${i * 12}ms` } as CSSProperties}
                data-source-id={p.id} data-score={p.score} data-audience={p.audience} data-x={p.x} data-y={p.y}
                aria-label={`${source.name}: ${cohort(p.score)}, ${p.score.toFixed(2)}, audience ${p.audience.toLocaleString("en")}`}
                aria-pressed={active?.id === p.id} tabIndex={focusId === p.id ? 0 : -1}
                onFocus={() => onSelect(p.id)} onPointerEnter={() => onSelect(p.id)} onClick={() => onSelect(p.id)} onKeyDown={e => navigate(e, i)}>
                <span className="sp-point-halo" /><span className="sp-point-core" />
                <span className="sp-point-label" aria-hidden="true" data-side={label.side} data-pos={label.pos}>{markLabel(source)}</span>
              </button>;
            })}
            <div className="sp-x-labels" aria-hidden="true"><span>Left −1</span><span>Center 0</span><span>Right +1</span></div>
          </div>
          <div className="sp-floor" aria-hidden="true" />
        </div>
      </> : <div className="sp-empty"><strong>Audience plot unavailable</strong><p>Sources need both a rating and a cited audience estimate to appear here. Available ratings remain in the source list.</p></div>}
      {selected && <div className="sp-inspector" data-source-id={selected.id}>
        <div className="sp-source-heading"><span className="sp-label">Selected source</span><h3>{selected.name}</h3><span className="sp-source-domain">{selected.domain}</span>{usedLabel(selected) && <span className="sp-source-used">{usedLabel(selected)}</span>}</div>
        <div className="sp-reading" key={`${selected.id}-${mode}`}>
          <div><span className="sp-label">Editorial position</span><strong className={score === null ? "" : `sp-value-${cohort(score).toLowerCase()}`}>{score === null ? "Unrated" : `${score > 0 ? "+" : ""}${score.toFixed(2)}`}</strong><span>{score === null ? "Rating not supplied" : cohort(score)}</span></div>
          <div><span className="sp-label">Audience estimate</span><strong>{selected.audience !== null && selected.audience >= 0 && audienceUrl ? compact(selected.audience) : "Not supplied"}</strong>{audienceUrl && <a href={audienceUrl} target="_blank" rel="noopener noreferrer">Audience source ↗</a>}<span>{selected.audience_as_of ? `As of ${selected.audience_as_of}` : "Reporting date not supplied"}</span></div>
        </div>
      </div>}
      {/* A story's few sources are often all plotted (2026-10-27, Anastasia/Claude Code): the second sentence only when some are not. */}
      <p className="sp-footnote">Logarithmic audience scale · supplied estimates only.{sources.length > geometry.points.length && <>{" "}{sources.length - geometry.points.length} {sources.length - geometry.points.length === 1 ? "source is" : "sources are"} not plotted; inspect their supplied values below.</>}</p>
    </div>
  );
}
