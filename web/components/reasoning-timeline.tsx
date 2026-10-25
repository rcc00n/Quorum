"use client";
import { useState } from "react";
import Link from "next/link";
import type { ReasoningRun } from "@/lib/reasoning";
import { recordedLoops, loopPairs, stageName } from "@/lib/reasoning-trace";
export function previewHref(run: ReasoningRun, event?: string) {
  return (
    "/preview/reasoning?" +
    new URLSearchParams({
      date: run.edition_date,
      version: String(run.version),
      ...(event ? { event } : {}),
    })
  );
}
export function ReasoningTimeline({
  run,
  currentEvent = "",
}: {
  run: ReasoningRun;
  currentEvent?: string;
}) {
  // DECISION(2026-10-24, rcc00n/Codex): an event deep-link starts with that event's trace.
  // Why: the roundup investigation link must not initially mix other events' checks.
  const [event, setEvent] = useState(currentEvent),
    [node, setNode] = useState(""),
    [loop, setLoop] = useState("");
  const steps = run.trace || [],
    nodes = [...new Set(steps.map((s) => s.node))];
  const events = [
    ...run.stories.map((s) => ({ id: s.event_id, title: s.headline })),
    ...run.roundup.groups.flatMap((g) =>
      g.items.map((i) => ({ id: i.event_id, title: i.line })),
    ),
  ];
  const scoped = steps.filter((s) => !event || s.event_id === event),
    loops = recordedLoops(scoped),
    selectedLoop = loopPairs.find((p) => p.id === loop);
  const filtered = steps
    .map((s, index) => ({ ...s, index }))
    .filter(
      (s) =>
        (!event || s.event_id === event) &&
        (!node || s.node === node) &&
        (!selectedLoop ||
          (selectedLoop.nodes as readonly string[]).includes(s.node)),
    );
  function selectNode(n: string) {
    setLoop("");
    setNode(node === n ? "" : n);
    inspectResults();
  }
  function inspectResults() {
    requestAnimationFrame(() => {
      const result = document.getElementById("reasoning-trace-results");
      result?.focus({ preventScroll: true });
      result?.scrollIntoView({
        block: "start",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    });
  }
  function selectEvent(id: string) {
    setEvent(id);
  }
  return (
    <section id="reasoning-timeline" tabIndex={-1} aria-labelledby="reasoning-timeline-title" className="r-section">
      <p className="eyebrow">RECORDED EXECUTION · NOT LIVE INFERENCE</p>
      <h2 id="reasoning-timeline-title">Investigation Timeline</h2>
      <p>
        Research can return for more evidence. A rejected draft can return for
        revision. Explore what this recorded run actually did.
      </p>
      <div className="r-trace-scope">
        <label>
          Investigate an event
          <select
            aria-label="Trace event filter"
            value={event}
            onChange={(e) => selectEvent(e.target.value)}
          >
            <option value="">All events and run steps</option>
            {events.map((e) => (
              <option key={e.id} value={e.id}>
                {e.title}
              </option>
            ))}
          </select>
        </label>
        {currentEvent && (
          <button
            className="r-text-button"
            onClick={() => {
              selectEvent(currentEvent);
              setNode("");
              setLoop("");
            }}
          >
            {run.stories.some((story) => story.event_id === currentEvent) ? "This story’s steps" : "This event’s steps"}
          </button>
        )}
      </div>
      {!!steps.length && (
        <>
          <div className="r-loop-overview" aria-label="Recorded feedback loops">
            {loops.map((pair) => {
              const active = loop === pair.id;
              return (
                <div key={pair.id} className={active ? "r-loop-selected" : ""}>
                  <p className="eyebrow">{pair.title}</p>
                  <h3>{pair.purpose}</h3>
                  <div className="r-loop-path">
                    {pair.nodes.map((n) => (
                      <button
                        key={n}
                        disabled={!scoped.some((s) => s.node === n)}
                        aria-pressed={node === n}
                        onClick={() => selectNode(n)}
                      >
                        <small>
                          {scoped.filter((s) => s.node === n).length} recorded
                          steps
                        </small>
                        {stageName(n)}
                      </button>
                    ))}
                    <svg
                      viewBox="0 0 400 110"
                      preserveAspectRatio="none"
                      aria-hidden="true"
                    >
                      <defs>
                        <marker
                          id={"r-arrow-" + pair.id}
                          markerWidth="7"
                          markerHeight="7"
                          refX="5"
                          refY="3.5"
                          orient="auto"
                        >
                          <path
                            d="M0 0L6 3.5L0 7"
                            fill="none"
                            stroke="currentColor"
                          />
                        </marker>
                      </defs>
                      {pair.forward > 0 && (
                        <path
                          d="M162 28H238"
                          markerEnd={`url(#r-arrow-${pair.id})`}
                        />
                      )}
                      {pair.returns.length > 0 && (
                        <path
                          className="r-return-path"
                          d="M320 53V75Q320 92 300 92H100Q80 92 80 75V58"
                          markerEnd={`url(#r-arrow-${pair.id})`}
                        />
                      )}
                    </svg>
                    <span className="r-loop-iterations">
                      {pair.returns.length
                        ? `↶ ${[...new Set(pair.returns.map((r) => `Iteration ${r.from} → ${r.to}`))].join(" · ")}`
                        : "No recorded return"}
                    </span>
                  </div>
                  <div className="r-loop-caption">
                    <span>
                      <strong>{pair.returns.length}</strong> recorded{" "}
                      {pair.returns.length === 1 ? "return" : "returns"}
                      <small>
                        Iterations{" "}
                        {pair.iterations.join(", ") || "not supplied"}
                      </small>
                    </span>
                    <button
                      className="r-text-button"
                      aria-pressed={active}
                      aria-label={`Show ${pair.title.toLowerCase()} loop`}
                      onClick={() => {
                        setNode("");
                        setLoop(active ? "" : pair.id);
                        inspectResults();
                      }}
                    >
                      {active ? "Show all stages" : "Show loop steps"}{" "}
                      <span aria-hidden="true">↓</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="help r-graph-key">
            Arrows connect consecutive recorded stages within the same event or
            run scope, not data dependencies. Choose a stage or loop to inspect
            its decisions.
          </p>
          <details className="r-stage-disclosure">
            <summary>
              {new Set(scoped.map((s) => s.node)).size} recorded stages{" "}
              <span>Explore the full stage index</span>
            </summary>
            <ol className="r-stage-index">
              {nodes.map((n) => (
                <li key={n}>
                  <button
                    disabled={!scoped.some((s) => s.node === n)}
                    aria-pressed={node === n}
                    onClick={() => selectNode(n)}
                  >
                    <strong>{stageName(n)}</strong>
                    <small>
                      {n} · {scoped.filter((s) => s.node === n).length} steps
                    </small>
                  </button>
                </li>
              ))}
            </ol>
          </details>
        </>
      )}
      <div className="r-trace-controls">
        <label>
          Recorded stage
          <select
            aria-label="Trace node filter"
            value={node}
            onChange={(e) => {
              setLoop("");
              setNode(e.target.value);
            }}
          >
            <option value="">All stages</option>
            {nodes.map((n) => (
              <option key={n} value={n}>
                {stageName(n)} · {n}
              </option>
            ))}
          </select>
        </label>
        {(event || node || loop) && (
          <button
            className="r-text-button"
            onClick={() => {
              selectEvent("");
              setNode("");
              setLoop("");
            }}
          >
            Clear filters · all {steps.length} steps
          </button>
        )}
      </div>
      <p
        id="reasoning-trace-results"
        className="help"
        role="status"
        tabIndex={-1}
      >
        {filtered.length} of {steps.length} recorded steps
        {selectedLoop ? ` · ${selectedLoop.title}` : ""} ·{" "}
        {steps.reduce((sum, s) => sum + s.duration_ms, 0)} ms total recorded
        duration. Zero is displayed as supplied.
      </p>
      {!steps.length ? (
        <p className="r-unavailable">No execution trace supplied.</p>
      ) : (
        <ol className="r-trace">
          {filtered.map((s) => (
            <li key={s.index} className={s.iteration > 1 ? "r-repeat" : ""}>
              <details>
                <summary>
                  <span className="r-step-index">
                    {String(s.index + 1).padStart(2, "0")}
                  </span>
                  <span>
                    <strong>
                      {stageName(s.node)}{" "}
                      <span className="r-iteration">
                        Iteration {s.iteration}
                        {s.iteration > 1 ? " · repeat" : ""}
                      </span>
                    </strong>
                    <span className="r-step-decision">{s.decision}</span>
                    <small>
                      {s.event_id
                        ? events.find((e) => e.id === s.event_id)?.title ||
                          s.event_id
                        : "Run-wide step"}
                    </small>
                  </span>
                  <span className="r-disclosure-icon" aria-hidden="true">
                    +
                  </span>
                </summary>
                <div className="r-trace-body">
                  <p className="eyebrow">Recorded reason</p>
                  <p>{s.reason || "No reason supplied."}</p>
                  {s.detail?.map((d, i) => <div key={i}><p>{d.text}</p><small>{d.reason}</small></div>)}
                  <small>
                    Node: {s.node} · {s.duration_ms} ms · Model:{" "}
                    {s.model || "Not supplied"}
                  </small>
                  {s.event_id ? (
                    <Link href={previewHref(run, s.event_id)}>
                      Event {s.event_id} →
                    </Link>
                  ) : (
                    <span>Run-wide step</span>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ol>
      )}
      {steps.length > 0 && !filtered.length && (
        <p>No steps match these filters.</p>
      )}
      <p className="help">
        Snapshot order, not timestamps. No claim-to-step links or private agent
        thoughts are inferred. Durations and model names are displayed only as
        supplied.
      </p>
    </section>
  );
}
