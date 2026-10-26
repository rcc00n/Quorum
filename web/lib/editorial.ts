// Optional presentation model, not an upstream API or a new production input schema.
import type { Event, Snapshot } from "./api";
export type EditorialPhoto = {
  url: string;
  source_url: string;
  license_url: string;
  license: string;
  credit: string;
  caption: string;
  rights_confirmed: boolean;
};
export type ArticlePresentation = {
  reading_minutes?: number;
  paragraphs: {
    kind: "fact" | "context" | "statement" | "not_confirmed";
    text: string;
    claim_ids: string[];
  }[];
  photo?: EditorialPhoto | null;
};
export type EditionPresentation = {
  topic_id: string;
  date: string;
  completion: "complete" | "partial";
  quiet_day: boolean;
  summary: string;
  // Supplied by the login-only reader for installed reasoning editions; absent on the proposal store.
  provisional?: boolean;
  corpus_as_of_utc?: string | null;
  edition_window_utc?: [string, string];
  closed_edition?: boolean;
  warnings?: string[];
  roundup: {
    name: string;
    items: {
      event_id: string | null;
      text: string;
      status: "attributed" | "disputed" | "unknown" | "established";
      label?: string;
      line_source?: string | null;
      needs_review?: boolean | null;
      sources: { title: string; url: string }[];
    }[];
  }[];
};
export function visibleStories(
  events: Event[],
  day: string,
  topic: string,
  followed: string[],
) {
  const counts = new Map<string, number>();
  return events.filter((e) => {
    if (
      e.date !== day ||
      (topic ? e.topic_id !== topic : !followed.includes(e.topic_id))
    )
      return false;
    const count = counts.get(e.topic_id) || 0;
    counts.set(e.topic_id, count + 1);
    return count < 10;
  });
}
export function isQuietDay(snapshot: Snapshot, edition: EditionPresentation) {
  return (
    ["available", "demo"].includes(snapshot.status) &&
    snapshot.publication?.status === "available" &&
    edition.completion === "complete" &&
    edition.quiet_day &&
    !snapshot.errors?.length &&
    !snapshot.events.some(
      (e) => e.date === edition.date && e.topic_id === edition.topic_id,
    )
  );
}
export function readableArticle(event: Event) {
  const article = event.article,
    claims = event.analysis?.claims;
  if (!article?.paragraphs.length || !claims) return false;
  const lookup = new Map(claims.map((c) => [c.id, c]));
  let previous = 0;
  return article.paragraphs.every((p) => {
    const order =
      p.kind === "statement" ? 1 : p.kind === "not_confirmed" ? 2 : 0;
    if (order < previous || !p.text.trim() || !p.claim_ids.length) return false;
    previous = order;
    return p.claim_ids.every((id) => {
      const claim = lookup.get(id);
      return (
        claim &&
        (order === 0
          ? claim.status === "established"
          : order === 1
            ? claim.status === "attributed" && !!claim.attribution?.speaker
            : ["unknown", "disputed"].includes(claim.status))
      );
    });
  });
}
export function licensedPhoto(photo: EditorialPhoto) {
  try {
    const urls = [photo.url, photo.source_url, photo.license_url].map(
      (u) => new URL(u),
    );
    if (
      !photo.rights_confirmed ||
      !photo.credit.trim() ||
      !photo.caption.trim() ||
      !photo.license.trim() ||
      urls.some(
        (u) =>
          u.protocol !== "https:" || !!u.username || !!u.password || !!u.port,
      )
    )
      return false;
    const allowed = (host: string) =>
      host.endsWith(".gov") ||
      host === "commons.wikimedia.org" ||
      host === "upload.wikimedia.org";
    return (
      allowed(urls[0].hostname) &&
      allowed(urls[1].hostname) &&
      /^(public domain|CC0-1\.0|CC-BY-4\.0|CC-BY-SA-4\.0)$/i.test(
        photo.license,
      ) &&
      (urls[2].hostname === "creativecommons.org" ||
        urls[2].hostname.endsWith(".gov") ||
        urls[2].hostname === "commons.wikimedia.org")
    );
  } catch {
    return false;
  }
}
