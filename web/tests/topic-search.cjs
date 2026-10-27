// Unit checks for the topic matcher used by the first-setup form and the settings topic picker.
//   node web/tests/topic-search.cjs
const assert = require("assert");
const path = require("path");
const { pathToFileURL } = require("url");

(async () => {
  const { matchTopics, normalize, words } = await import(pathToFileURL(path.join(__dirname, "..", "lib", "topic-search.mjs")).href);
  const catalog = [
    { id: "russia-ukraine-war", name: "Russia–Ukraine war" },
    { id: "immigration-southern-border", name: "Immigration and the southern border" },
    { id: "tariffs-trade-war-china", name: "Tariffs and the trade war with China" },
    { id: "ai-regulation-export-controls", name: "AI regulation and export controls" },
    { id: "climate-policy", name: "Climate policy" },
  ];
  const ids = (q) => matchTopics(catalog, q).map((t) => t.id);

  assert.strictEqual(normalize("Russia–Ukraine  War!"), "russia ukraine war");
  assert.deepStrictEqual(words("war in the Ukraine"), ["war", "ukraine"]);
  assert.deepStrictEqual(ids(""), catalog.map((t) => t.id), "empty query returns the catalog in order");
  assert.deepStrictEqual(ids("   "), catalog.map((t) => t.id));
  assert.deepStrictEqual(ids("ukraine war"), ["russia-ukraine-war"], "word order does not matter");
  assert.deepStrictEqual(ids("war in Ukraine"), ["russia-ukraine-war"], "stop words are ignored");
  assert.deepStrictEqual(ids("UKRAIN"), ["russia-ukraine-war"], "case and a word prefix");
  assert.deepStrictEqual(ids("trade war"), ["tariffs-trade-war-china"], "a phrase inside the name");
  assert.deepStrictEqual(ids("war"), ["russia-ukraine-war", "tariffs-trade-war-china"], "one word, two topics, catalog order within a rank");
  assert.deepStrictEqual(ids("Climate policy"), ["climate-policy"], "exact name");
  assert.deepStrictEqual(ids("climate"), ["climate-policy"]);
  assert.deepStrictEqual(ids("elections"), [], "no match is an empty list, never an invented topic");
  assert.deepStrictEqual(ids("ai"), ["ai-regulation-export-controls"], "two-letter words count");
  console.log("PASS: topic matcher (" + 13 + " cases)");
})().catch((e) => {
  console.error("FAIL: " + e.message);
  process.exit(1);
});
