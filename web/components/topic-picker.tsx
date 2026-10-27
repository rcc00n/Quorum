"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { Topic } from "@/lib/api";
import { matchTopics } from "@/lib/topic-search.mjs";
import { ThemeToggle } from "./theme-toggle";
import "@/app/gate.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the picker searches the catalog the backend already serves and
// never pretends to create a topic. The portal's preferences endpoint accepts catalog ids only and no
// topic-write bridge exists (docs/PORTAL_INTEGRATION.md › Topic writes and delivery); a typed topic that is
// not in the catalog gets an honest sentence, and the bridge is proposed to the web owner in Issue #2.
// Why: DECISIONS › User account and interface item 2 (search over existing names first) and the guard that
// backend, API and lib/api.ts change only with the owner's agreement.

type Props = {
  topics: Topic[];
  catalogRevision?: string | null;
  selected: string[];
  onChange: (ids: string[]) => void;
  busy: boolean;
  onSave: () => void;
  saveLabel: string;
  /** The board's panel (cabinet pass, 2026-10-27): no explanatory lines, the search placeholder is the one hint. */
  compact?: boolean;
};

export function TopicPicker({ topics, catalogRevision, selected, onChange, busy, onSave, saveLabel, compact = false }: Props) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => matchTopics(topics, query) as Topic[], [topics, query]);
  const byId = useMemo(() => new Map(topics.map((t) => [t.id, t.name])), [topics]);
  const trimmed = query.trim();

  function toggle(id: string, on: boolean) {
    onChange(on ? [...selected.filter((x) => x !== id), id] : selected.filter((x) => x !== id));
  }
  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (trimmed && matches.length) {
      toggle(matches[0].id, true);
      setQuery("");
    }
  }

  return (
    <section className={compact ? "topic-picker tp tp-compact" : "topic-picker tp"}>
      <div className="tp-head">
        <h2>Your topics</h2>
        <span className="tp-count">{`${selected.length} selected`}</span>
      </div>
      {!compact && (
        <p className="tp-lead">
          Type a topic to find it in the catalog, or pick it from the list. The agents collect and verify stories on
          your topics alone.
        </p>
      )}
      {catalogRevision && <p className="help">Team catalog snapshot · definitions only. Live analysis is pending.</p>}
      {topics.length ? (
        <>
          <label className="tp-search">
            <span>Search topics</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={compact ? "Search the catalog, Enter adds the first match" : "Type a topic and press Enter"}
              autoComplete="off"
              aria-describedby={compact ? undefined : "tp-search-hint"}
            />
          </label>
          {!compact && (
            <p id="tp-search-hint" className="tp-hint">
              Enter adds the first match. One at a time: a war, a country, a court case, a company, an industry.
            </p>
          )}
          {selected.length > 0 && (
            <ul className="tp-chips" role="list" aria-label="Chosen topics">
              {selected.map((id) => (
                <li key={id}>
                  <span>{byId.get(id) ?? id}</span>
                  <button type="button" aria-label={`Remove ${byId.get(id) ?? id}`} onClick={() => toggle(id, false)}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          {matches.length ? (
            <div className="topic-options" role="group" aria-label="Topics in the catalog">
              {matches.map((t) => (
                <label key={t.id} className="topic-option">
                  <input type="checkbox" checked={selected.includes(t.id)} onChange={(e) => toggle(t.id, e.target.checked)} />
                  <span>{t.name}</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="tp-none" role="status">
              {`“${trimmed}” is not in the catalog yet. New topics are added by the team and collected from the collector's next pass; this page cannot create them.`}
            </p>
          )}
        </>
      ) : (
        <aside className="notice tp-notice">
          <strong>The topic catalog is not connected yet.</strong>
          <p>You can return here to choose topics once the catalog is available.</p>
        </aside>
      )}
      {!compact && (
        <p className="tp-foot">
          {`${selected.length} ${selected.length === 1 ? "topic" : "topics"} · up to ten stories a day for each, none on a quiet day · change them any time`}
        </p>
      )}
      <button type="button" className="button tp-button" disabled={busy} onClick={onSave}>
        {saveLabel}
      </button>
    </section>
  );
}

export function FirstSetup({
  loading,
  error,
  onRetry,
  message,
  demo,
  children,
}: {
  loading: boolean;
  error: string;
  onRetry: () => void;
  message: string;
  demo: boolean;
  children: React.ReactNode;
}) {
  return (
    <main id="main" className="gate setup">
      <header className="gate-head">
        <Link href="/" className="gate-masthead" aria-label="Quorum home">
          Quorum
        </Link>
        <div className="gate-actions">
          <ThemeToggle />
          <Link href="/dashboard" className="gate-link">
            Later
          </Link>
        </div>
      </header>
      <div className="gate-body">
        <p className="gate-kicker">First setup · topics</p>
        <h1>What do you want to follow?</h1>
        <p className="gate-lead">
          Name it in your own words. The agents collect and verify stories on your topics alone, then show how
          outlets across the spectrum read each one.
        </p>
        {demo && (
          <p className="message" role="status">
            DEMO · Fictional interface fixture. Not verified news or live findings.
          </p>
        )}
        {message && (
          <p className="message" role="status">
            {message}
          </p>
        )}
        {loading ? (
          <p className="gate-lead">Loading your account…</p>
        ) : error ? (
          <div className="gate-error">
            <p className="message error" role="alert">
              {error}
            </p>
            <button type="button" className="button" onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : (
          children
        )}
      </div>
    </main>
  );
}
