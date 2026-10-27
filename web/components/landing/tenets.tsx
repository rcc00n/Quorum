"use client";
import { useEffect, useState } from "react";

// DECISION(2026-10-27, Anastasia/Claude Code; landing after the deck): the hero's lead is one sentence typed once
// and left standing, in a box of fixed height (two lines) so the page below never moves; without motion the sentence
// stands at once. The sentence is the deck's tenet and claims nothing beyond DECISIONS (a blind second check by a
// second model). Why: Anastasia's reviews of 2026-10-27: the deck's typewriter shifted the text under it, and a
// rotating lead pulled attention; "typed once and left as typed".
const CHAR_MS = 34;

export function Tenets({ text, className = "" }: { text: string; className?: string }) {
  const [shown, setShown] = useState(text);
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) return;
    let cancelled = false, timer = 0, i = 0;
    setShown(""); setTyping(true);
    const step = () => {
      if (cancelled) return;
      i += 1; setShown(text.slice(0, i));
      if (i < text.length) timer = window.setTimeout(step, CHAR_MS); else setTyping(false);
    };
    timer = window.setTimeout(step, 600);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [text]);
  return (
    <div className={`lp-tenets ${className}`}>
      <p className="lp-tenets-live" aria-hidden="true">
        {shown}
        {typing && <span className="lp-caret" />}
      </p>
      <p className="lp-tenets-static">{text}</p>
    </div>
  );
}
