"use client";
import { useState } from "react";
import Link from "next/link";
import type { ReasoningRun } from "@/lib/reasoning";
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
export function ReasoningTimeline({ run }: { run: ReasoningRun }) {
  const [event, setEvent] = useState(""),
    [node, setNode] = useState("");
  const steps = run.trace || [],
    nodes = [...new Set(steps.map((s) => s.node))];
  const events = [
    ...run.stories.map((s) => ({ id: s.event_id, title: s.headline })),
    ...run.roundup.groups.flatMap((g) =>
      g.items.map((i) => ({ id: i.event_id, title: i.line })),
    ),
  ];
  const filtered = steps
    .map((s, index) => ({ ...s, index }))
    .filter(
      (s) => (!event || s.event_id === event) && (!node || s.node === node),
    );
  return (
    <section id="reasoning-timeline" className="r-section">
      <p className="eyebrow">RECORDED EXECUTION · NOT LIVE INFERENCE</p>
      <h2>Investigation Timeline</h2>
      <p>
        Public-safe recorded decisions in snapshot order. No timestamps or
        private reasoning were supplied.
      </p>
      <div className="r-loop-overview" aria-label="Recorded feedback loops">
        {[
          ["research", "verify"],
          ["write", "critique"],
        ].map(([a, b]) => {
          const count = steps.filter(
            (s) => [a, b].includes(s.node) && s.iteration > 1,
          ).length;
          return (
            <div key={a}>
              <strong>
                {a} ⇄ {b}
              </strong>
              <span>{count} recorded repeat steps</span>
              <small>
                {count
                  ? "Repeated iterations are present in the snapshot."
                  : "No repeated iteration supplied."}
              </small>
            </div>
          );
        })}
      </div>
      <div className="r-trace-controls">
        <label>
          Event filter
          <select
            aria-label="Trace event filter"
            value={event}
            onChange={(e) => setEvent(e.target.value)}
          >
            <option value="">All events and run steps</option>
            {events.map((e) => (
              <option key={e.id} value={e.id}>
                {e.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Node filter
          <select
            aria-label="Trace node filter"
            value={node}
            onChange={(e) => setNode(e.target.value)}
          >
            <option value="">All nodes</option>
            {nodes.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="help" role="status">
        {filtered.length} of {steps.length} recorded steps ·{" "}
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
                    <strong>{s.node.replaceAll("_", " ")}</strong>
                    <small>
                      Iteration {s.iteration}{" "}
                      {s.iteration > 1 ? "· feedback / re-check" : ""} ·{" "}
                      {s.duration_ms} ms
                    </small>
                  </span>
                  <span aria-hidden="true">+</span>
                </summary>
                <div className="r-trace-body">
                  <p>{s.decision}</p>
                  <p className="help">{s.reason}</p>
                  <small>Model: {s.model || "Not supplied"}</small>
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
        No claim-to-step links are inferred: this trace supplies event
        associations only.
      </p>
    </section>
  );
}
