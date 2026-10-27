"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Snapshot } from "@/lib/api";
import { workspaceItems, searchWorkspace } from "@/lib/workspace-nav";
import type { WorkspaceItem } from "@/lib/workspace-nav";

export function WorkspaceNavigator({ data, day, currentId, revision, disabled }: {
  data: Snapshot | null; day: string; currentId?: string; revision?: string; disabled: boolean;
}) {
  const router = useRouter(), dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLInputElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false), [query, setQuery] = useState(""), [index, setIndex] = useState(0);
  const results = searchWorkspace(workspaceItems(data, day, currentId, revision), query);
  const selected = Math.min(index, Math.max(0, results.length - 1));
  function show() { if (disabled || !dialog.current || dialog.current.open) return; setQuery(""); setIndex(0); dialog.current.showModal(); setOpen(true); input.current?.focus(); }
  useEffect(() => {
    if (disabled) dialog.current?.close();
    function shortcut(e: globalThis.KeyboardEvent) { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && !disabled) { e.preventDefault(); show(); } }
    window.addEventListener("keydown", shortcut); return () => window.removeEventListener("keydown", shortcut);
  }, [disabled]);
  function choose(item: WorkspaceItem) {
    dialog.current?.close();
    const url = new URL(item.href, location.origin);
    if (url.pathname === location.pathname && url.search === location.search && url.hash) location.hash = url.hash;
    else router.push(item.href);
  }
  useEffect(() => { dialog.current?.querySelector<HTMLElement>(`#workspace-result-${selected}`)?.scrollIntoView({ block: "nearest" }); }, [selected]);
  return <>
    <button type="button" ref={trigger} className="workspace-search" aria-label="Search workspace" aria-haspopup="dialog" aria-expanded={open} aria-keyshortcuts="Control+k Meta+k" onClick={show} disabled={disabled}>Search <kbd>⌘ K</kbd></button>
    <dialog className="workspace-search-dialog" ref={dialog} aria-labelledby="workspace-search-title" onClose={() => { setOpen(false); trigger.current?.focus(); }} onClick={e => { if (e.target === e.currentTarget) dialog.current?.close(); }}>
      <header><span id="workspace-search-title">Go anywhere</span><button type="button" aria-label="Close search" onClick={() => dialog.current?.close()}>Esc</button></header>
      <label className="workspace-search-label" htmlFor="workspace-search-input">Search this edition and workspace</label>
      <input ref={input} id="workspace-search-input" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="workspace-search-results" aria-activedescendant={results.length ? `workspace-result-${selected}` : undefined}
        autoComplete="off" placeholder="A story, a topic, a different view…" maxLength={100} value={query} onChange={e => { setQuery(e.target.value); setIndex(0); }} onKeyDown={e => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (results.length) setIndex((selected + (e.key === "ArrowDown" ? 1 : -1) + results.length) % results.length); }
          else if (e.key === "Enter") { e.preventDefault(); if (results[selected]) choose(results[selected]); }
        }} />
      <div id="workspace-search-results" role="listbox" aria-label="Workspace destinations" className="workspace-search-results">
        {results.map((item, i) => <button key={item.id} type="button" role="option" id={`workspace-result-${i}`} aria-selected={selected === i} tabIndex={-1} onPointerMove={() => setIndex(i)} onClick={() => choose(item)}>
          <span className="workspace-result-index">{String(i + 1).padStart(2, "0")}</span><span><strong>{item.label}</strong><small>{item.detail}</small></span><span aria-hidden="true">↗</span>
        </button>)}
      </div>
      {!results.length && <p className="workspace-search-empty" role="status">No matching destination in the loaded edition. Try a topic or page name.</p>}
      <footer><span>↑ ↓ to explore · Enter to open</span><span>Loaded edition only · no new analysis</span></footer>
    </dialog>
  </>;
}
