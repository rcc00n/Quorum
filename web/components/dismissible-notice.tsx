"use client";
import { useLayoutEffect, useState } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

// DECISION(2026-10-27, Anastasia/Claude Code): the two notices at the top of the workspace, the AI headline notice and
// the DEMO notice, carry a close button (a white × on an ink circle, 24 px seen, 32 px to hit, named for its notice).
// Closing hides that notice until the end of the browser session (sessionStorage, one key per notice), so every new
// visit, a judge's included, shows both again; without storage it stays hidden until reload. The AI notice renders
// visible on the server and on first paint (no reader misses it to hydration); the DEMO notice appears when the
// fictional data loads. Why: Anastasia, 2026-10-27: "a white × in a circle on both notices, so they can be closed too",
// to fit the interface. Canonical: docs/DECISIONS.md › User account and interface, item 12.
//
// Every workspace route renders its own Portal, so a client navigation mounts the notice afresh. The keys closed in this
// page's lifetime are remembered here, outside React, so a later mount starts hidden instead of flashing for a frame; the
// set is empty on a full load (the server markup and hydration agree) and doubles as the store when sessionStorage throws.
const closedThisPage = new Set<string>();

export function DismissibleNotice({ storageKey, closeLabel, className, role, children }: {
  storageKey: string; closeLabel: string; className: string; role: "note" | "status"; children: ReactNode;
}) {
  const key = `quorum.notice.${storageKey}.closed`;
  const [open, setOpen] = useState(() => !closedThisPage.has(key));
  // A layout effect hides a notice closed earlier in the session before the browser paints this mount.
  useLayoutEffect(() => {
    try {
      if (window.sessionStorage.getItem(key) === "1") {
        closedThisPage.add(key);
        setOpen(false);
      }
    } catch {
      // No storage (private mode, blocked site data): the in-page set keeps it closed until reload.
    }
  }, [key]);
  if (!open) return null;
  function close() {
    closedThisPage.add(key);
    try {
      window.sessionStorage.setItem(key, "1");
    } catch {
      // Without storage the notice is hidden until reload only.
    }
    // The button leaves the page with its notice; focus moves to the main column so keyboard and screen-reader users
    // keep their place (#main is the skip link's target and takes focus programmatically).
    document.getElementById("main")?.focus({ preventScroll: true });
    setOpen(false);
  }
  return (
    <div className={`notice-dismissible ${className}`} role={role}>
      <div className="notice-body">{children}</div>
      <button type="button" className="notice-close" aria-label={closeLabel} onClick={close}>
        <span aria-hidden="true"><X size={14} strokeWidth={2.5} /></span>
      </button>
    </div>
  );
}
