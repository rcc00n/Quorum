import type {
  ReasoningStory,
  ReasoningRun,
  ReasoningPreview,
} from "./reasoning";
import type { ArticlePresentation, EditionPresentation } from "./editorial";
import type { StructuredAnalysis, Publication } from "./analysis";
export type User = {
  username: string;
  name: string;
  email: string;
  topics: string[];
  is_staff: boolean;
};
export type Topic = { id: string; name: string };
export type Source = {
  id: string;
  name: string;
  domain: string;
  audience: number | null;
  audience_source_url?: string | null;
  audience_as_of?: string | null;
  kind?: "agency" | "outlet" | "official" | "military";
  tier?: "major" | "minor" | null;
  independence_group?: string;
  rating_provenance?: {
    allsides: string | null;
    mbfc: string | null;
    adfontes: string | null;
  };
  allsides: number | null;
  mbfc: number | null;
  adfontes: number | null;
};
export type Evidence = {
  text: string;
  explanation: string;
  sources: { title: string; url: string }[];
};
// Portal view model; reasoning-owned 1.0 consumer types live in reasoning.ts.
export type Event = {
  reasoning?: ReasoningStory;
  article?: ArticlePresentation;
  analysis?: StructuredAnalysis;
  id: string;
  topic_id: string;
  date: string;
  title: string;
  summary: string;
  importance: { label: string; explanation: string } | null;
  established: Evidence[];
  statements: Evidence[];
  disputed: Evidence[];
  unknown: Evidence[];
  coverage: Evidence[];
  sources: Source[];
};
export type Snapshot = {
  reasoning?: ReasoningRun;
  preview?: ReasoningPreview;
  editions?: EditionPresentation[];
  publication?: Publication;
  errors?: { code: string; message: string; event_id: string | null }[];
  catalog_revision?: string | null;
  status: string;
  topics: Topic[];
  sources: Source[];
  events: Event[];
  digests: { date: string; topic_id: string; summary: string }[];
};
let csrfToken = "";
export async function api<T>(path: string, payload?: unknown): Promise<T> {
  if (payload !== undefined && !csrfToken) await session();
  const res = await fetch("/api/" + path + "/", {
    method: payload === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers:
      payload === undefined
        ? {}
        : { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const data = await res
    .json()
    .catch(() => ({ error: "The service could not complete this request." }));
  if (!res.ok)
    throw new Error(
      data.error || "The service could not complete this request.",
    );
  if (data.csrfToken) csrfToken = data.csrfToken;
  return data as T;
}
export async function session() {
  return api<{ user: User | null; csrfToken: string }>("session");
}
export async function feed(day: string, topic: string): Promise<Snapshot> {
  const res = await fetch(
    `/api/feed/?date=${encodeURIComponent(day)}&topic=${encodeURIComponent(topic)}`,
    { cache: "no-store" },
  );
  if (!res.ok)
    throw new Error("Your brief could not be loaded. Please try again.");
  return res.json();
}
export async function eventSnapshot(
  id: string,
  day?: string,
  revision?: string,
): Promise<Snapshot> {
  const query = new URLSearchParams();
  if (day) query.set("date", day);
  if (revision) query.set("revision", revision);
  const res = await fetch(`/api/events/${encodeURIComponent(id)}/?${query}`, {
    cache: "no-store",
  });
  if (!res.ok)
    throw new Error("This analysis could not be loaded. Please try again.");
  return res.json();
}
export function rating(source: Source, mode: string): number | null {
  const scores = [source.allsides, source.mbfc, source.adfontes].filter(
    (s): s is number => s !== null && Number.isFinite(s),
  );
  return mode === "average"
    ? scores.length
      ? scores.reduce((a, b) => a + b, 0) / scores.length
      : null
    : source[mode as "allsides" | "mbfc" | "adfontes"];
}
export function cohort(score: number) {
  return score <= -0.25 ? "Left" : score >= 0.25 ? "Right" : "Center";
}
export function safeUrl(url: string) {
  try {
    const u = new URL(url);
    return ["https:", "http:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
