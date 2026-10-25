import type { Snapshot } from "../lib/api";
/** DEMO ONLY: fictional, deliberately no political ratings or claimed verified news. */
export const demo: Snapshot = {
  status: "demo",
  topics: [{ id: "demo-civic", name: "DEMO · Civic life" }],
  sources: [],
  digests: [],
  events: [
    {
      id: "demo-event",
      topic_id: "demo-civic",
      date: "2026-10-22",
      title: "DEMO · A fictional community meeting",
      summary:
        "A fictional example for interface testing. This is not a news report.",
      importance: null,
      established: [],
      statements: [
        {
          text: "DEMO · An attributed statement would appear here.",
          explanation: "Fictional example; not verified evidence.",
          sources: [],
        },
      ],
      disputed: [],
      unknown: [
        {
          text: "DEMO · The outcome has not been supplied.",
          explanation: "Uncertainty stays visible.",
          sources: [],
        },
      ],
      coverage: [],
      sources: [],
    },
  ],
};
