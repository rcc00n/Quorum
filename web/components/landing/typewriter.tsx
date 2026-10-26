"use client";
import { useEffect, useState } from "react";

// DECISION(2026-10-25, Anastasia/Claude Code): the typewriter rewrites real titles only, one into the next,
// and the full list stays in the DOM for readers without motion and for screen readers; the animated
// span is aria-hidden. Why: motion must never be the only way to read a fact, and the lines are evidence.
const CHAR_MS = 38;
const HOLD_MS = 1700;
const ERASE_MS = 14;

function commonPrefix(a: string, b: string) {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

export function Typewriter({ lines, className }: { lines: string[]; className?: string }) {
  const [text, setText] = useState(lines[0] ?? "");
  const [active, setActive] = useState(0);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (reduced || lines.length < 2) return;
    let cancelled = false;
    let timer = 0;
    const schedule = (fn: () => void, ms: number) => {
      timer = window.setTimeout(() => {
        if (!cancelled) fn();
      }, ms);
    };
    const run = (index: number) => {
      const from = lines[index];
      const next = (index + 1) % lines.length;
      const to = lines[next];
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
  }, [lines, reduced]);

  return (
    <div className={className}>
      {reduced ? (
        <ol className="lp-type-static">
          {lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ol>
      ) : (
        <>
          <p className="lp-type-live" aria-hidden="true">
            <span>{text}</span>
            <span className="lp-caret" />
          </p>
          <ol className="lp-sr-only">
            {lines.map((l, i) => (
              <li key={l} aria-current={i === active ? "true" : undefined}>
                {l}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
