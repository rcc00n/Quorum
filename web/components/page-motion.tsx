"use client";
import { useEffect } from "react";
import "@/app/page-motion.css";

// DECISION(2026-10-26, rcc00n/Codex): observers only add presentation; unrevealed content stays readable.
// Why: scrolling, reduced-motion settings or a missing observer must never hide news or block a link.
export function PageMotion({ root, ready = true, epoch }: { root: string; ready?: boolean; epoch?: unknown }) {
  useEffect(() => {
    if (!ready) return;
    const parent = document.querySelector<HTMLElement>(root);
    if (!parent) return;
    const motion = window.matchMedia("(prefers-reduced-motion: no-preference)");
    const pointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const revealed: HTMLElement[] = [];
    const observer = window.IntersectionObserver && motion.matches ? new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) { (entry.target as HTMLElement).dataset.revealed = "true"; observer?.unobserve(entry.target); }
      });
    }, { threshold: 0, rootMargin: "0px 0px -24px 0px" }) : null;
    // The board's head and the page headings (title, date control, "+ Add topics") stay still; only what sits
    // below the rule arrives (Anastasia, second cabinet pass 2026-10-27: no reveal on the head when the date changes).
    parent.querySelectorAll<HTMLElement>(".lp-hero-text, .lp-sheet, .landing main > section:not(#hero), .tb-section, .r-section, .analysis-section, .spectrum-modern").forEach(el => {
      if (!observer || el.parentElement?.closest('.q-reveal')) return;
      el.classList.add('q-reveal');el.style.setProperty('--q-delay', `${Math.min(revealed.length, 4) * 45}ms`);
      revealed.push(el);observer.observe(el);
    });
    const surfaces = Array.from(parent.querySelectorAll<HTMLElement>(".lp-sheet, .tb-card-lead .tb-card-link"));
    surfaces.forEach(el => el.classList.add('q-depth'));
    let active: HTMLElement | null = null, frame = 0;
    function reset() {
      if (frame) cancelAnimationFrame(frame); frame = 0;
      active?.style.setProperty('--q-rx', '0deg');active?.style.setProperty('--q-ry', '0deg');active = null;
    }
    function move(event: PointerEvent) {
      if (!motion.matches || !pointer.matches) { reset(); return; }
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>('.q-depth') : null;
      if (target !== active) { reset(); active = target; }
      if (!active || frame) return;
      const { clientX, clientY } = event;
      frame = requestAnimationFrame(() => {
        frame = 0; if (!active) return;
        const box = active.getBoundingClientRect();
        active.style.setProperty('--q-rx', `${((clientY - box.top) / box.height - .5) * -3}deg`);
        active.style.setProperty('--q-ry', `${((clientX - box.left) / box.width - .5) * 4}deg`);
      });
    }
    parent.addEventListener('pointermove', move, { passive: true });
    parent.addEventListener('pointerleave', reset);
    return () => {
      reset();observer?.disconnect();parent.removeEventListener('pointermove', move);parent.removeEventListener('pointerleave', reset);
      surfaces.forEach(el => el.classList.remove('q-depth'));
      revealed.forEach(el => { el.classList.remove('q-reveal');delete el.dataset.revealed;el.style.removeProperty('--q-delay'); });
    };
  }, [root, ready, epoch]);
  return null;
}
