"use client";
import { useEffect } from "react";

// DECISION(2026-10-26, Anastasia/Claude Code): one flag on <html>, data-scrolled, tells the header of every route
// whether the page has scrolled under it; a passive scroll listener sets it through requestAnimationFrame, with a
// 4 px threshold so a page resting at the top stays clear. Why: the landing header is a server component and the
// app bar is Vadim's markup; a flag on the root styles both (app/header.css) without touching their markup.
export function ScrollState() {
  useEffect(() => {
    let frame = 0;
    const apply = () => {
      frame = 0;
      document.documentElement.dataset.scrolled = window.scrollY > 4 ? "true" : "false";
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(apply);
    };
    apply();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}
