// Pure presentation invariants; synthetic TEST IDs, never real news or ratings.
const assert = require("node:assert/strict");
const {
  visibleStories,
  isQuietDay,
  readableArticle,
  licensedPhoto,
} = require("../lib/editorial.ts");
const event = { id: "TEST-event", topic_id: "TEST-topic", date: "2026-10-22" };
const edition = {
  topic_id: "TEST-topic",
  date: event.date,
  completion: "complete",
  quiet_day: true,
};
const snapshot = {
  status: "available",
  publication: { status: "available" },
  events: [],
};
assert.equal(isQuietDay(snapshot, edition), true);
for (const status of ["pending", "error", "partial", "stale"])
  assert.equal(
    isQuietDay({ ...snapshot, publication: { status } }, edition),
    false,
  );
assert.equal(isQuietDay({ ...snapshot, status: "pending" }, edition), false);
assert.equal(isQuietDay({ ...snapshot, events: [event] }, edition), false);
assert.equal(
  isQuietDay(snapshot, { ...edition, completion: "partial" }),
  false,
);
assert.equal(visibleStories([], event.date, "TEST-topic", []).length, 0);
assert.equal(visibleStories([event], event.date, "TEST-topic", []).length, 1);
const many = ["TEST-topic", "TEST-other"].flatMap((topic_id) =>
  Array.from({ length: 12 }, (_, i) => ({
    ...event,
    id: topic_id + i,
    topic_id,
  })),
);
assert.equal(
  visibleStories(many, event.date, "", ["TEST-topic", "TEST-other"]).length,
  20,
);
const article = {
  paragraphs: [
    { kind: "context", text: "TEST supplied prose", claim_ids: ["TEST-claim"] },
  ],
};
assert.equal(readableArticle({ ...event, article }), false);
assert.equal(
  readableArticle({
    ...event,
    article,
    analysis: { claims: [{ id: "TEST-claim", status: "unknown" }] },
  }),
  false,
);
assert.equal(
  readableArticle({
    ...event,
    article,
    analysis: { claims: [{ id: "TEST-claim", status: "established" }] },
  }),
  true,
);
const photo = {
  url: "https://upload.wikimedia.org/TEST-not-a-real-photo",
  source_url: "https://commons.wikimedia.org/wiki/TEST",
  license_url: "https://creativecommons.org/licenses/by/4.0/",
  license: "CC-BY-4.0",
  credit: "TEST",
  caption: "TEST",
  rights_confirmed: true,
};
// Shape/allowlist checks only; no image is fetched or asserted licensed by this test.
assert.equal(licensedPhoto(photo), true);
assert.equal(licensedPhoto({ ...photo, rights_confirmed: false }), false);
assert.equal(licensedPhoto({ ...photo, credit: "" }), false);
assert.equal(
  licensedPhoto({ ...photo, url: "https://example.com/unapproved" }),
  false,
);
assert.equal(
  licensedPhoto({ ...photo, license: "all rights reserved" }),
  false,
);
console.log(
  "PASS: TEST editorial cap per topic, quiet/pending/error/stale guards, context claim status, photo metadata/host checks (no photo fetched)",
);
