"use client";
import Link from "next/link";
import type { Snapshot, User, Event } from "@/lib/api";
import type { EditionPresentation } from "@/lib/editorial";
import { visibleStories, isQuietDay } from "@/lib/editorial";
import { describeCut, utcLabel } from "@/lib/edition-cut.mjs";
import "@/app/today.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the daily brief is a board of topic sections, each on its own
// warm tint, each with one horizontal row of rounded matte cards (the stories above the bar, then the "Also
// today" roundup, or the quiet-day card, or the waiting card), in the manner of Apple News' Today but on this
// portal's paper and without photographs (none we may use; the card is made of its text). Everything on a
// card comes from the published snapshot: title, standfirst, importance label, source count, reading time;
// nothing is invented, the fictional fixture keeps its DEMO label, a quiet day says so, and a missing
// edition says when its cut is. Why: Anastasia's brief of 2026-10-26 (the personal page should resemble
// Apple News: rounded cards, topic headings, sections told apart by tint, the menu at the top).

type Props = {
  data: Snapshot | null;
  user: User | null;
  day: string;
  today: string;
  onDay: (day: string) => void;
};

function longDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

function roundupCount(edition?: EditionPresentation) {
  return edition ? edition.roundup.reduce((n, g) => n + g.items.length, 0) : 0;
}

function StoryCard({ event, topicName, day }: { event: Event; topicName: string; day: string }) {
  const minutes = event.article?.reading_minutes;
  const meta = [
    event.importance?.label ?? "Importance not supplied",
    `${event.sources.length} ${event.sources.length === 1 ? "source" : "sources"}`,
    typeof minutes === "number" ? `${minutes} min` : null,
  ].filter(Boolean);
  return (
    <li className="tb-card">
      <Link href={`/events/${encodeURIComponent(event.id)}?date=${day}`} className="tb-card-link">
        <span className="tb-card-topic">{topicName}</span>
        <h3>{event.title}</h3>
        <p>{event.summary}</p>
        <span className="tb-card-meta">{meta.join(" · ")}</span>
      </Link>
    </li>
  );
}

export function TodayBoard({ data, user, day, today, onDay }: Props) {
  const followedIds = user?.topics ?? [];
  const topics = (data?.topics ?? []).filter((t) => followedIds.includes(t.id));
  const stories = visibleStories(data?.events ?? [], day, "", followedIds);
  const status = data?.status ?? "pending";
  const { cut, passed, hoursUntil } = describeCut(day);
  const isToday = day === today;
  const n = topics.length;

  return (
    <div className="tb">
      <header className="tb-head">
        <div>
          <p className="tb-kicker">
            {`Edition ${day} · `}
            <span>{`${n} ${n === 1 ? "topic" : "topics"} in your brief`}</span>
          </p>
          <h1>
            {isToday ? "Today" : "Edition"} <span className="tb-date">{longDate(day)}</span>
          </h1>
          <p className="tb-status">
            {status === "pending"
                ? "No editions have been published to this portal yet. No published events are available for this edition."
                : stories.length === 0
                  ? "No published events are available for this edition."
                  : `${stories.length} ${stories.length === 1 ? "story" : "stories"} above the bar across your topics.`}
          </p>
        </div>
        <div className="tb-controls">
          <label className="tb-date-pick">
            Edition date
            <input type="date" value={day} max={today} onChange={(e) => onDay(e.target.value || today)} />
          </label>
          <Link href="/settings" className="tb-link">
            My topics
          </Link>
        </div>
      </header>

      {n === 0 && (
        <section className="tb-section tb-tint-2" aria-labelledby="tb-none">
          <div className="tb-section-head">
            <h2 id="tb-none">You follow no topics yet.</h2>
            <p className="tb-section-meta">The board fills one section per topic you choose.</p>
          </div>
          <Link href="/onboarding" className="button tb-choose">
            Choose your topics
          </Link>
        </section>
      )}

      {topics.map((t, i) => {
        const own = stories.filter((e) => e.topic_id === t.id);
        const edition = data?.editions?.find((e) => e.topic_id === t.id && e.date === day);
        const quiet = !!(data && edition && isQuietDay(data, edition));
        const below = roundupCount(edition);
        const meta = quiet
          ? "No story crossed the bar today"
          : own.length
            ? `${own.length} ${own.length === 1 ? "story" : "stories"} today`
            : passed
              ? `Waiting for the ${day} edition`
              : `Edition cut in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`;
        return (
          <section key={t.id} className={`tb-section tb-tint-${(i % 4) + 1}`} aria-labelledby={`tb-${t.id}`}>
            <div className="tb-section-head">
              <h2 id={`tb-${t.id}`}>
                <Link href={`/topics/${encodeURIComponent(t.id)}?date=${day}`}>{t.name}</Link>
              </h2>
              <p className="tb-section-meta">{meta}</p>
            </div>
            <ul className="tb-row" role="list" aria-label={`${t.name}: stories of the ${day} edition`}>
              {own.map((e) => (
                <StoryCard key={e.id} event={e} topicName={t.name} day={day} />
              ))}
              {quiet && (
                <li className="tb-card tb-card-quiet">
                  <div className="tb-card-link">
                    <span className="tb-card-topic">{t.name}</span>
                    <h3>No story crossed the bar today.</h3>
                    <p>Nothing was large enough on the rubric; the roundup carries the day.</p>
                  </div>
                </li>
              )}
              {edition && (
                <li className="tb-card tb-card-roundup">
                  <Link href={`/topics/${encodeURIComponent(t.id)}?date=${day}`} className="tb-card-link">
                    <span className="tb-card-topic">Also today</span>
                    <h3>{`${below} ${below === 1 ? "event" : "events"} below the bar`}</h3>
                    <p>{edition.roundup.map((g) => g.name).filter(Boolean).join(" · ") || "One line each, with source and status."}</p>
                    <span className="tb-card-meta">{edition.completion === "partial" ? "partial edition" : "complete edition"}</span>
                  </Link>
                </li>
              )}
              {!own.length && !quiet && !edition && (
                <li className="tb-card tb-card-wait">
                  <div className="tb-card-link">
                    <span className="tb-card-topic">{t.name}</span>
                    <h3>{passed ? `The ${longDate(day)} edition is not published yet.` : `The ${longDate(day)} edition has not been cut yet.`}</h3>
                    <p>{`Cut 05:30 New York · ${utcLabel(cut)} · ${passed ? "passed" : `in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`}. The team starts one run per topic after the cut; nothing is started from this page.`}</p>
                    <span className="tb-card-meta">waiting</span>
                  </div>
                </li>
              )}
            </ul>
          </section>
        );
      })}

      <p className="tb-fine">
        Stories are selected by an absolute impact bar, up to ten a day per topic and none on a quiet day; everything
        below the bar is in the roundup. New topics start thin until feeds accumulate.
      </p>
    </div>
  );
}
