"use client";
import { useEffect, useState } from "react";

// DECISION(2026-10-25, Anastasia/Claude Code): the typewriter rewrites real titles only, one into the next,
// and the full list stays in the DOM for readers without motion and for screen readers. Why: motion must never
// be the only way to read a fact, and the lines are evidence.
// DECISION(2026-10-26, Anastasia/Claude Code): both branches are server-rendered and a CSS media query chooses
// which one is visible, so a reader who prefers reduced motion gets the static staircase on first paint, with no
// hydration swap; the effect only decides whether to animate. The counter names the revision and the document
// id of the line being typed, without a denominator: the sample holds three versions and does not say the chain
// ended there.
const CHAR_MS = 38;
const HOLD_MS = 1700;
const ERASE_MS = 14;

export type TypewriterLine = { id: string; text: string };

function commonPrefix(a: string, b: string) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

export function Typewriter({ lines, className }: { lines: TypewriterLine[]; className?: string }) {
  const [text, setText] = useState(lines[0]?.text ?? "");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches || lines.length < 2) return;
    let cancelled = false;
    let timer = 0;
    const schedule = (fn: () => void, ms: number) => {
      timer = window.setTimeout(() => {
        if (!cancelled) fn();
      }, ms);
    };
    const run = (index: number) => {
      const from = lines[index].text;
      const next = (index + 1) % lines.length;
      const to = lines[next].text;
      const keep = commonPrefix(from, to);
      let current = from;
      const erase = () => {
        if (current.length > keep) {
          current = current.slice(0, -1);
          setText(current);
          schedule(erase, ERASE_MS);
        } else {
          setActive(next);
          type();
        }
      };
      const type = () => {
        if (current.length < to.length) {
          current = to.slice(0, current.length + 1);
          setText(current);
          schedule(type, CHAR_MS);
        } else {
          schedule(() => run(next), HOLD_MS);
        }
      };
      schedule(erase, HOLD_MS);
    };
    run(0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [lines]);

  return (
    <div className={className}>
      <p className="lp-type-live" aria-hidden="true">
        <span className="lp-rev">
          rev {active + 1} · doc {lines[active]?.id}
        </span>
        <span className="lp-type-text">
          {text}
          <span className="lp-caret" />
        </span>
      </p>
      <ol className="lp-type-static" role="list">
        {lines.map((l, i) => (
          <li key={l.id} aria-current={i === active ? "true" : undefined}>
            <span className="lp-type-id">
              <span className="lp-sr-only">rev {i + 1}, doc </span>
              {l.id}
            </span>
            <span className="lp-type-title">{l.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
