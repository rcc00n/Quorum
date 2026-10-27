// The run graph of docs/ARCHITECTURE.md § 5, redrawn for the landing: the fifteen nodes top to bottom in run order,
// the three loops and the escalation branch, with the seven step captions aligned to the nodes they explain. A
// server component: the layout is computed from fixtures/landing/graph.json here, nothing moves at run time.
// DECISION(2026-10-27, Anastasia/Claude Code): drawn after LangGraph Studio's graph view in the landing's identity:
// rounded boxes with the node's name in the mono and its lane under it, grey fill for a node that calls a model and
// paper for a node that is code only, start and end as grey pills, solid edges for the run's path and dashed ones
// for an edge that runs on a condition (the mermaid's dotted edges), orthogonal routing. Edges carry no text: the
// conditions and the limits are written in the captions beside the step, where there is room to read them. The
// edges are exactly the mermaid's of § 5; the nodes come from graph.json, which landing.cjs checks against § 5.
// Why: Anastasia, 2026-10-27: "the architecture section like the LangGraph Studio graphs, in our style, with
// captions, and it must be a redrawn graph, true to the content". The lane per node restates reasoning.toml
// [models] as docs/ARCHITECTURE.md § 5's node table reads it (default lane → Nemotron 3.5 Lightning; fact_checker
// and reviewer → Nemotron 3 Ultra 550B); Meterless is named in #runs only.
import type { ReactNode } from "react";

export type GraphStep = { n: string; title: string; nodes: string[]; lead: string; body: string; rules?: ReactNode[] };

const LIGHTNING = "Nemotron 3.5 Lightning", ULTRA = "Nemotron 3 Ultra 550B", CODE = "code";
const LANE: Record<string, string> = {
  plan: CODE, cluster: LIGHTNING, score_importance: LIGHTNING, extract_claims: LIGHTNING, research: LIGHTNING,
  verify: CODE, fact_check: ULTRA, adjudicate: CODE, review_disputed: ULTRA, escalate: CODE,
  frame: LIGHTNING, write: LIGHTNING, critique: CODE, roundup: LIGHTNING, publish: LIGHTNING,
};

// § 5's edges. `cond` marks a dotted edge of the mermaid: it runs only when its condition holds.
type Edge = { from: string; to: string; cond?: boolean; route: "down" | "loop" | "bypass-left" | "to-right" | "across" | "from-right" };
const EDGES: Edge[] = [
  { from: "plan", to: "cluster", route: "down" },
  { from: "cluster", to: "score_importance", route: "down" },
  { from: "score_importance", to: "extract_claims", route: "down" },
  { from: "extract_claims", to: "research", route: "down" },
  { from: "research", to: "verify", route: "down" },
  { from: "verify", to: "research", cond: true, route: "loop" },
  { from: "verify", to: "fact_check", cond: true, route: "down" },
  { from: "fact_check", to: "adjudicate", route: "down" },
  { from: "adjudicate", to: "review_disputed", cond: true, route: "down" },
  { from: "adjudicate", to: "escalate", cond: true, route: "to-right" },
  { from: "adjudicate", to: "frame", cond: true, route: "bypass-left" },
  { from: "review_disputed", to: "escalate", cond: true, route: "across" },
  { from: "review_disputed", to: "frame", cond: true, route: "down" },
  { from: "escalate", to: "frame", route: "from-right" },
  { from: "frame", to: "write", route: "down" },
  { from: "write", to: "critique", route: "down" },
  { from: "critique", to: "write", cond: true, route: "loop" },
  { from: "critique", to: "roundup", cond: true, route: "down" },
  { from: "roundup", to: "publish", route: "down" },
];
// escalate shares review_disputed's row, at the right: the branch out of the run's path.
const RIGHT_OF: Record<string, string> = { escalate: "review_disputed" };

const W = 400, BOX_W = 168, BOX_H = 44, CX = 120, CX_RIGHT = 310, PITCH = 68, MIN_BLOCK = 136, PILL_H = 28, TOP = 42;
const half = BOX_W / 2, hh = BOX_H / 2;
// The caption's height, estimated from its text at the narrowest desktop width of the caption column (about
// 440 px: 52 characters of the lead, 60 of the body, 66 of a rule line), so a block is never shorter than the
// caption beside it; the grid row may still grow (minmax) if a line wraps earlier, at the cost of alignment below.
function captionHeight(s: GraphStep) {
  const lines = (text: string, perLine: number) => Math.max(1, Math.ceil(text.length / perLine));
  const rules = (s.rules ?? []).reduce<number>((sum, r) => sum + lines(ruleText(r), 66) * 19 + 8, 0);
  return 2 + 24 + 6 + lines(s.lead, 52) * 22 + 4 + lines(s.body, 60) * 21 + rules + 16;
}
function ruleText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(ruleText).join("");
  if (node && typeof node === "object" && "props" in node) return ruleText((node as { props: { children?: ReactNode } }).props.children);
  return "";
}

export function RunGraph({ nodes, steps, startLabel, endLabel }: { nodes: string[]; steps: GraphStep[]; startLabel: string; endLabel: string }) {
  for (const n of nodes) if (!(n in LANE)) throw new Error(`landing graph: no lane for node ${n}`);
  for (const e of EDGES) if (!nodes.includes(e.from) || !nodes.includes(e.to)) throw new Error(`landing graph: edge names an unknown node ${e.from} → ${e.to}`);
  // Blocks: one per step, as tall as its rows of nodes or the caption's minimum, the nodes centred in the block.
  const pos = new Map<string, { x: number; y: number }>();
  const blocks: number[] = [];
  let top = TOP;
  for (const s of steps) {
    const rows = s.nodes.filter((n) => !(n in RIGHT_OF));
    const h = Math.max(rows.length * PITCH, MIN_BLOCK, captionHeight(s));
    const first = top + (h - (rows.length - 1) * PITCH) / 2;
    rows.forEach((n, i) => pos.set(n, { x: CX, y: first + i * PITCH }));
    for (const n of s.nodes) if (n in RIGHT_OF) pos.set(n, { x: CX_RIGHT, y: pos.get(RIGHT_OF[n])!.y });
    blocks.push(h);
    top += h;
  }
  const H = top + 12 + PILL_H + 2;
  const at = (n: string) => { const p = pos.get(n); if (!p) throw new Error(`landing graph: unplaced node ${n}`); return p; };
  const first = at(nodes[0]), last = at(nodes[nodes.length - 1]);
  const path = (e: Edge) => {
    const a = at(e.from), b = at(e.to);
    switch (e.route) {
      case "down": return `M ${a.x} ${a.y + hh} V ${b.y - hh - 1}`;
      case "loop": { const x = a.x + half; return `M ${x} ${a.y} H ${x + 16} Q ${x + 22} ${a.y} ${x + 22} ${a.y - 6} V ${b.y + 6} Q ${x + 22} ${b.y} ${x + 16} ${b.y} H ${x + 1}`; }
      case "to-right": return `M ${a.x + half} ${a.y} H ${b.x} V ${b.y - hh - 1}`;
      case "across": return `M ${a.x + half} ${a.y} H ${b.x - half - 1}`;
      case "bypass-left": return `M ${a.x - half} ${a.y} H 16 V ${b.y - hh - 12} H ${b.x - 32} V ${b.y - hh - 1}`;
      case "from-right": return `M ${a.x} ${a.y + hh} V ${b.y - hh - 12} H ${b.x + 32} V ${b.y - hh - 1}`;
    }
  };
  const marker = (n: string) => (LANE[n] === CODE ? "○" : "●");
  const describe = `${nodes.length} nodes top to bottom in run order: ${nodes.join(", ")}. Loops: verify back to research, critique back to write, adjudicate to review_disputed. An event with no confirmed claim goes from adjudicate or review_disputed to escalate and on to frame, out of the stories. Dashed edges run on a condition.`;
  return (
    <div className="lp-graph">
      <svg className="lp-graph-svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-labelledby="lp-graph-title lp-graph-desc">
        <title id="lp-graph-title">The run graph</title>
        <desc id="lp-graph-desc">{describe}</desc>
        <defs>
          <marker id="lp-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0.5 L 8 4 L 0 7.5 z" className="lp-arrow" />
          </marker>
        </defs>
        <g className="lp-pill" transform={`translate(${first.x - 70}, 2)`}>
          <rect width={140} height={PILL_H} rx={PILL_H / 2} />
          <text x={70} y={PILL_H / 2 + 3.5} textAnchor="middle">{startLabel}</text>
        </g>
        <path className="lp-edge" markerEnd="url(#lp-arrow)" d={`M ${first.x} ${2 + PILL_H} V ${first.y - hh - 1}`} />
        {EDGES.map((e) => (
          <path key={`${e.from}-${e.to}`} className={e.cond ? "lp-edge lp-edge-cond" : "lp-edge"} markerEnd="url(#lp-arrow)" d={path(e)} data-from={e.from} data-to={e.to} />
        ))}
        <path className="lp-edge" markerEnd="url(#lp-arrow)" d={`M ${last.x} ${last.y + hh} V ${top + 11}`} />
        <g className="lp-pill" transform={`translate(${last.x - 70}, ${top + 12})`}>
          <rect width={140} height={PILL_H} rx={PILL_H / 2} />
          <text x={70} y={PILL_H / 2 + 3.5} textAnchor="middle">{endLabel}</text>
        </g>
        {nodes.map((n) => {
          const p = at(n);
          return (
            <g key={n} className={LANE[n] === CODE ? "lp-node lp-node-code" : "lp-node lp-node-model"} transform={`translate(${p.x - half}, ${p.y - hh})`} data-node={n}>
              <rect width={BOX_W} height={BOX_H} rx={8} />
              <text x={14} y={19} className="lp-node-name">{`${marker(n)} ${n}`}</text>
              <text x={14} y={34} className="lp-node-lane">{LANE[n]}</text>
            </g>
          );
        })}
      </svg>
      <ol className="lp-graph-captions" role="list" style={{ gridTemplateRows: blocks.map((h) => `minmax(${h}px, auto)`).join(" ") }}>
        {steps.map((s) => (
          <li key={s.n} className="lp-gc">
            <div className="lp-gc-head"><span className="lp-gc-n">{s.n}</span><h3>{s.title}</h3></div>
            <p className="lp-gc-nodes">{s.nodes.map((n) => `${marker(n)} ${n}`).join(" · ")}</p>
            <p className="lp-gc-lead">{s.lead}</p>
            <p className="lp-gc-body">{s.body}</p>
            {s.rules?.map((r, i) => <p key={i} className="lp-gc-rule">{r}</p>)}
          </li>
        ))}
      </ol>
    </div>
  );
}
