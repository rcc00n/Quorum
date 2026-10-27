"use client";
import { useEffect, useRef } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";
import type { Source } from "@/lib/api";
import { cohort, rating, safeUrl } from "@/lib/api";
import { spectrumGeometry } from "@/lib/spectrum-geometry";

const compact = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
export function SpectrumField({ sources, mode, selectedId, onSelect }: {
  sources: Source[]; mode: string; selectedId: string | null; onSelect: (id: string) => void;
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
        <span>{geometry.points.length} plotted · {rated.length} rated · {sources.length} in registry</span>
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
              return <button type="button" className={`sp-point sp-point-${lean}`} key={p.id}
                ref={node => { if (node) buttons.current.set(p.id, node); else buttons.current.delete(p.id); }}
                style={{ left: `${p.x}%`, top: `${p.y}%`, "--sp-delay": `${i * 12}ms` } as CSSProperties}
                data-source-id={p.id} data-score={p.score} data-audience={p.audience} data-x={p.x} data-y={p.y}
                aria-label={`${source.name}: ${cohort(p.score)}, ${p.score.toFixed(2)}, audience ${p.audience.toLocaleString("en")}`}
                aria-pressed={active?.id === p.id} tabIndex={focusId === p.id ? 0 : -1}
                onFocus={() => onSelect(p.id)} onPointerEnter={() => onSelect(p.id)} onClick={() => onSelect(p.id)} onKeyDown={e => navigate(e, i)}>
                <span className="sp-point-halo" /><span className="sp-point-core" />
              </button>;
            })}
            <div className="sp-x-labels" aria-hidden="true"><span>Left −1</span><span>Center 0</span><span>Right +1</span></div>
          </div>
          <div className="sp-floor" aria-hidden="true" />
        </div>
      </> : <div className="sp-empty"><strong>Audience plot unavailable</strong><p>Sources need both a rating and a cited audience estimate to appear here. Available ratings remain in the source list.</p></div>}
      {selected && <div className="sp-inspector" data-source-id={selected.id}>
        <div className="sp-source-heading"><span className="sp-label">Selected source</span><h3>{selected.name}</h3><span className="sp-source-domain">{selected.domain}</span></div>
        <div className="sp-reading" key={`${selected.id}-${mode}`}>
          <div><span className="sp-label">Editorial position</span><strong className={score === null ? "" : `sp-value-${cohort(score).toLowerCase()}`}>{score === null ? "Unrated" : `${score > 0 ? "+" : ""}${score.toFixed(2)}`}</strong><span>{score === null ? "Rating not supplied" : cohort(score)}</span></div>
          <div><span className="sp-label">Audience estimate</span><strong>{selected.audience !== null && selected.audience >= 0 && audienceUrl ? compact(selected.audience) : "Not supplied"}</strong>{audienceUrl && <a href={audienceUrl} target="_blank" rel="noopener noreferrer">Audience source ↗</a>}<span>{selected.audience_as_of ? `As of ${selected.audience_as_of}` : "Reporting date not supplied"}</span></div>
        </div>
      </div>}
      <p className="sp-footnote">Logarithmic audience scale · supplied estimates only. {sources.length - geometry.points.length} {sources.length - geometry.points.length === 1 ? "source is" : "sources are"} not plotted; inspect their supplied values below.</p>
    </div>
  );
}
