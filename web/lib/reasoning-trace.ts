import type { ReasoningStep } from "./reasoning";
const stageNames: Record<string, string> = {
  plan: "Plan",
  cluster: "Group events",
  score_importance: "Assess impact",
  extract_claims: "Extract claims",
  research: "Research",
  verify: "Verify",
  fact_check: "Independent check",
  adjudicate: "Resolve verdicts",
  frame: "Compare coverage",
  write: "Write",
  critique: "Critique",
  roundup: "Roundup",
  publish: "Snapshot output",
};
export const stageName = (node: string) =>
  stageNames[node] || node.replaceAll("_", " ");
// DECISION(2026-10-24, rcc00n/Codex): scope skipped checks to the recorded event.
// Why: a producer roundup verdict must not imply independent verification.
export function roundupCheckNotice(steps: ReasoningStep[] | undefined, eventId: string) {
  return steps?.some((s) => s.event_id === eventId && s.node === "fact_check" && /^skipped\s*:/i.test(s.decision.trim()))
    ? "Independent check skipped; not double-checked."
    : "Independent verification is not established by this roundup entry; claim evidence is not supplied.";
}
export const loopPairs = [
  {
    id: "research",
    nodes: ["research", "verify"],
    title: "Research & verification",
    purpose: "Re-check the evidence",
  },
  {
    id: "writing",
    nodes: ["write", "critique"],
    title: "Writing & critique",
    purpose: "Revise the article",
  },
] as const;
// DECISION(2026-10-22, rcc00n/Codex): infer only recorded same-event A→B→A returns.
// Why: interleaved events and iteration numbers alone cannot establish an execution path.
export function recordedLoops(steps: ReasoningStep[]) {
  const scopes = new Map<string | null, ReasoningStep[]>();
  for (const step of steps) {
    if (!scopes.has(step.event_id)) scopes.set(step.event_id, []);
    scopes.get(step.event_id)!.push(step);
  }
  return loopPairs.map((pair) => {
    let forward = 0;
    const returns: { event: string | null; from: number; to: number }[] = [];
    for (const scope of scopes.values()) {
      for (let i = 0; i < scope.length - 1; i++) {
        const a = scope[i],
          b = scope[i + 1],
          c = scope[i + 2];
        if (a.node === pair.nodes[0] && b.node === pair.nodes[1]) {
          forward++;
          if (c?.node === a.node && c.iteration > a.iteration)
            returns.push({
              event: a.event_id,
              from: a.iteration,
              to: c.iteration,
            });
        }
      }
    }
    return {
      ...pair,
      forward,
      returns,
      iterations: [
        ...new Set(
          steps
            .filter((s) => (pair.nodes as readonly string[]).includes(s.node))
            .map((s) => s.iteration),
        ),
      ].sort((a, b) => a - b),
    };
  });
}
