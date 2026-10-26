// Matching typed text against the catalog's topic names, so an existing topic is found before anyone
// thinks of creating a second one ("war in Ukraine" finds "Russia–Ukraine war").
// DECISION(2026-10-26, Anastasia/Claude Code): case-, accent- and punctuation-insensitive; stop words and
// one-letter tokens are ignored; every remaining word of the query must start a word of the name (or be
// started by a name word of four letters or more); exact names rank first, phrases that start at a word
// boundary second, word matches third; an empty query returns the whole catalog in catalog order. Plain ESM so the same code
// runs in the browser and in `node web/tests/topic-search.cjs`. Why: DECISIONS › User account and interface
// item 2 asks for the existing topic to be offered before a new slug exists; the catalog is small, so a
// transparent rule beats a fuzzy score nobody can explain.
const STOP = new Set(["the", "a", "an", "of", "in", "on", "and", "or", "for", "to", "vs", "v", "at", "by", "with"]);

export function normalize(text) {
  return String(text ?? "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export function words(text) {
  return normalize(text)
    .split(" ")
    .filter((w) => w.length > 1 && !STOP.has(w));
}

export function matchTopics(topics, query) {
  const q = normalize(query);
  if (!q) return topics.slice();
  const qw = words(query);
  const scored = [];
  for (const topic of topics) {
    const name = normalize(topic.name);
    const nw = words(topic.name);
    let score = 0;
    if (name === q) score = 3;
    else if ((" " + name).includes(" " + q)) score = 2; // the query starts a word of the name, never sits inside one
    else if (qw.length && qw.every((w) => nw.some((x) => x.startsWith(w) || (x.length >= 4 && w.startsWith(x))))) score = 1;
    if (score) scored.push({ topic, score });
  }
  return scored.sort((a, b) => b.score - a.score).map((m) => m.topic);
}
