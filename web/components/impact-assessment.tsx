import type { Event } from "@/lib/api";

// DECISION(2026-10-27, rcc00n/Codex): visualize only a complete, internally consistent supplied rubric.
// Why: partial fields must not become an invented score. Ranges: DECISIONS › Selecting major news.
const dimensions = [
  ["legal_force", "Legal force", 2], ["reach", "Reach", 3],
  ["irreversibility", "Irreversibility", 2], ["confirmation", "Confirmation", 2],
] as const;
export function ImpactAssessment({ event }: { event: Event }) {
  const record = event.importance, rubric = event.reasoning?.rubric;
  const complete = rubric && dimensions.every(([key, , max]) => Number.isInteger(rubric[key]) && rubric[key] >= 0 && rubric[key] <= max)
    && Number.isInteger(rubric.total) && rubric.total === dimensions.reduce((sum, [key]) => sum + rubric[key], 0);
  if (!record && !complete) return null;
  return <details className="impact-assessment">
    <summary><strong>Impact</strong><span className="impact-summary-note">Selection rubric</span><span className="impact-toggle" aria-hidden="true">+</span></summary>
    {complete ? <div className="impact-overview">
      <div className="impact-total"><span>Recorded points</span><div><strong className="impact-total-value">{rubric.total}</strong><span> / 9</span></div><p>From this edition’s selection rubric.</p></div>
      <dl className="impact-dimensions">{dimensions.map(([key, label, max]) => <div className="impact-dimension" key={key} data-dimension={key}>
        <div><dt>{label}</dt><dd><strong>{rubric[key]}</strong> / {max}</dd></div>
        <div className="impact-steps" aria-hidden="true">{Array.from({ length: max }, (_, i) => <span className={i < rubric[key] ? "filled" : ""} key={i} />)}</div>
      </div>)}</dl>
    </div> : <p className="impact-original-label">{record?.label}</p>}
    <details className="impact-notes">
      <summary>Selection evidence and original notes <span aria-hidden="true">↗</span></summary>
      {complete && <dl className="impact-rationales">{dimensions.map(([key, label]) => <div key={key}><dt>{label}</dt><dd data-dimension={key}>{rubric.rationale?.[key] || "Rationale not supplied."}</dd></div>)}</dl>}
      {record && <div className="impact-original"><span>Original selection record</span><strong>{record.label}</strong><p>{record.explanation}</p></div>}
    </details>
  </details>;
}
