// The sources used for one story, for the story page's Map tab.
// DECISION(2026-10-27, Anastasia/Claude Code; supersedes the "registry context" sentence of the Reader workspace
// amendment, docs/DECISIONS.md › Stories as articles): the Map on a story plots the sources used for that story, not
// the whole registry. "Used" is two recorded facts and nothing inferred: the outlets whose reports the producer grouped
// into the event (`story.sources`, which reasoning's publish node fills from the event's clustered documents,
// nodes/publish.py, some read only by title; the portal binds them to registry rows as `event.sources`) and the registry
// outlets its claims' evidence quotes (`evidence.source_id`). The labels say which, in the producer's terms; nothing is
// called coverage, independence or audience of the event. The producer's covered/eligible counts stay in the Coverage
// tab and the whole registry stays on the Sources page. Why: Anastasia, 2026-10-27: the Map duplicated the Sources
// page; on a story it must show the sources used for this story.
import type { Event, Source } from "./api";

export type StorySource = Source & { used: { story: boolean; evidence: boolean } };
/** Which set a spectrum draws: the registry (the Sources page) or the sources used for one story (a story's Map). */
export type SpectrumScope = "registry" | "story";

/** The one line above a story's Map, on every story page: what the drawn sources are and what they are not. */
export const STORY_MAP_NOTE = "Outlets whose reports were grouped into this event, and outlets its evidence quotes. Audience is each outlet's overall cited estimate, not this story's readers; independence is judged in Evidence.";

/** How a source was used for the story, in words, or null for a registry row. */
export function usedLabel(source: Source): string | null {
  const used = (source as Partial<StorySource>).used;
  if (!used) return null;
  return [used.story ? "Grouped into this event" : null, used.evidence ? "Quoted in its evidence" : null].filter(Boolean).join(" · ") || null;
}

type StoryLike = Pick<Event, "sources" | "reasoning">;

/** Registry rows used for a story, in registry order, each marked with how it was used. A story source that the
 * registry lacks is kept as the portal supplied it; an evidence id the registry lacks is left out, since the registry
 * row is what carries the ratings and the audience the Map draws. Pure: the inputs are not modified. */
export function storySources(event: StoryLike, registry: Source[]): StorySource[] {
  const fromStory = new Set((event.sources || []).map((s) => s.id));
  const fromEvidence = new Set<string>();
  for (const claim of event.reasoning?.claims || [])
    for (const evidence of claim.evidence || [])
      if (evidence.source_id) fromEvidence.add(evidence.source_id);
  const known = new Set(registry.map((s) => s.id));
  const used = (id: string) => ({ story: fromStory.has(id), evidence: fromEvidence.has(id) });
  const rows: StorySource[] = registry
    .filter((s) => fromStory.has(s.id) || fromEvidence.has(s.id))
    .map((s) => ({ ...s, used: used(s.id) }));
  for (const s of event.sources || []) if (!known.has(s.id)) rows.push({ ...s, used: used(s.id) });
  return rows;
}
