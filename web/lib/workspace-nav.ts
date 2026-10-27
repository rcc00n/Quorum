import type { Snapshot } from "./api";
export type WorkspaceItem = { id: string; label: string; detail: string; href: string; keywords?: string; needsReview?: boolean };
export function workspaceItems(data: Snapshot | null, day: string, currentId?: string, revision?: string): WorkspaceItem[] {
  const items: WorkspaceItem[] = [
    { id: "today", label: "Today", detail: "Your daily brief", href: "/dashboard", keywords: "home news" },
    { id: "history", label: "History", detail: "Return to the viewed edition", href: `/history?date=${encodeURIComponent(data?.events.find(e => e.id === currentId)?.date || day)}`, keywords: "archive date" },
    { id: "sources", label: "Sources", detail: "Registry spectrum and audience", href: "/sources", keywords: "graph chart map political ratings" },
    { id: "topics", label: "My topics", detail: "Topics, profile and account", href: "/settings", keywords: "preferences password settings" },
  ];
  for (const topic of data?.topics || []) items.push({ id: `topic:${topic.id}`, label: topic.name, detail: "Topic · viewed edition", href: `/topics/${encodeURIComponent(topic.id)}?date=${encodeURIComponent(day)}` });
  for (const event of data?.events || []) {
    const href = `/events/${encodeURIComponent(event.id)}?date=${encodeURIComponent(event.date)}${event.id === currentId && revision ? `&revision=${encodeURIComponent(revision)}` : ""}`;
    items.push({ id: `event:${event.id}`, label: event.title, detail: `Story · ${event.date}`, href, needsReview: !!event.reasoning?.needs_review });
    if (event.id === currentId) for (const [view, label, keywords] of [
      ["evidence", "Evidence · this story", "claims citations reviewers"], ["coverage", "Coverage · this story", "perspectives framing"],
      ["map", "Source map · this story", "graph chart spectrum political audience"], ["trace", "Investigation · this story", "trace reasoning steps"],
    ]) items.push({ id: `view:${view}`, label, detail: event.title, href: `${href}#reader-${view}`, keywords, needsReview: !!event.reasoning?.needs_review });
  }
  return items;
}
const fold = (s: string) => s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
export function searchWorkspace(items: WorkspaceItem[], query: string) {
  const terms = fold(query.trim()).split(/\s+/).filter(Boolean);
  return items.filter(item => terms.every(term => fold(`${item.label} ${item.detail} ${item.keywords || ""}`).includes(term)))
    .sort((a, b) => Number(b.id === "view:map" && terms.some(t => /graph|chart|map|spectrum/.test(t))) - Number(a.id === "view:map" && terms.some(t => /graph|chart|map|spectrum/.test(t))))
    .slice(0, 10);
}
