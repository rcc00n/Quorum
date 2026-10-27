import Link from "next/link";
import type { Event } from "@/lib/api";
import { ReviewLabel } from "./story";
import { rubricTotal } from "./impact-assessment";

// DECISION(2026-10-27, Anastasia/Claude Code; second cabinet pass): the topic page lists its stories as rows in the
// manner of "Also today" (one low rounded row per story: the headline, the supplied Impact total in the mono when the
// rubric is complete, the review label when the producer flagged the story), and the story cards stay on Home only.
// Why: Anastasia, 2026-10-27: "rows like Also today on the topic; cards only on Home"; a topic page that repeated
// the board's cards read as Home.
export function TopicStories({ events, day }: { events: Event[]; day: string }) {
  return (
    <ul className="topic-stories" role="list">
      {events.map((e) => {
        const total = rubricTotal(e);
        return (
          <li className="topic-story" key={e.id}>
            <Link href={`/events/${encodeURIComponent(e.id)}?date=${day}`} className="topic-story-link">
              <span className="topic-story-title">{e.title}</span>
              {total !== null && <span className="topic-story-meta">{`Impact ${total} / 9`}</span>}
            </Link>
            {e.reasoning?.needs_review && <ReviewLabel />}
          </li>
        );
      })}
    </ul>
  );
}
