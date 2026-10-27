"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { Snapshot, Topic, User, Event } from "@/lib/api";
import { api } from "@/lib/api";
import { TopicPicker } from "./topic-picker";
import type { EditionPresentation } from "@/lib/editorial";
import { visibleStories, isQuietDay, licensedPhoto } from "@/lib/editorial";
import { describeCut, utcLabel } from "@/lib/edition-cut.mjs";
import { EditionNavigation } from "./edition-navigation";
import "@/app/today.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the daily brief is a board of topic sections on the white page,
// a hairline above each, each with one horizontal row of rounded translucent cards (the stories above the bar,
// then the "Also today" roundup, or the quiet-day card, or the waiting card), in the manner of Apple News'
// Today on this portal's paper. The first story of a section is the lead card, wider and taller than the
// rest. Every card reserves a photo area; it shows a picture only when the snapshot carries one that
// `licensedPhoto` accepts, with its credit, and stays an empty field otherwise (no stock photography).
// Everything else on a card comes from the published snapshot: title, standfirst, importance label, source
// count, reading time; nothing is invented, the fictional fixture keeps its DEMO label, a quiet day says so,
// and a missing edition says when its cut is. Why: Anastasia's brief of 2026-10-26 (the personal page should
// resemble Apple News: rounded cards, topic headings, the menu at the top) and her review the same day (no
// section tints, only the cards carry weight; a photo slot in each card; a larger lead card).

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

function StoryCard({ event, day, lead }: { event: Event; day: string; lead: boolean }) {
  const photo = event.article?.photo;
  const picture = photo && licensedPhoto(photo) ? photo : null;
  return (
    <li className={lead ? "tb-card tb-card-lead" : "tb-card"}>
      <Link href={`/events/${encodeURIComponent(event.id)}?date=${day}`} className={picture ? "tb-card-link" : "tb-card-link tb-card-link-blank"}>
        {/* The picture, or the blurred field without one, covers the whole card (app/today.css); the media slot
            only reserves the picture's height and holds the credit or the note. */}
        {picture && (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="tb-card-photo" src={picture.url} alt={picture.caption} />
        )}
        <div className={picture ? "tb-card-media" : "tb-card-media tb-card-media-missing"} aria-hidden={picture ? undefined : true}>
          {picture ? (
            <span className="tb-card-credit">{`Photo: ${picture.credit}`}</span>
          ) : (
            // The quieter version of the story page's missing-photo line (components/story.tsx PhotoMissing);
            // the whole area is decorative on a card, whose link text is the headline.
            <span className="tb-card-note">Imagine a photo here.</span>
          )}
        </div>
        {/* DECISION(2026-10-27, Anastasia/Claude Code; cabinet pass): the card is the picture and the headline,
            nothing else; the review label stays when the producer flagged the story (Yelysei's rule), the
            topic name, standfirst, importance, source count and minutes are read on the story page. Why:
            her review of 2026-10-27: more picture, a larger headline at the foot, no other text. */}
        <div className="tb-card-text">
          {event.reasoning?.needs_review && <span className="tb-card-review">Requires editorial review</span>}
          <h3>{event.title}</h3>
        </div>
      </Link>
    </li>
  );
}

// DECISION(2026-10-27, Anastasia/Claude Code; cabinet pass after untitled.stream): the board carries the
// user's topics itself. One "+ Add topics" control at the top opens the same picker the first setup uses,
// saving through the existing preferences call and reloading the page; the settings page keeps name, email
// and password only. Under the title one mono line of metadata replaces the prose status lines (the smoke
// test's sentences are kept verbatim inside it). Why: Anastasia's review of 2026-10-27: the page should show
// the title with the date and then the topics with their news, nothing else; topics are managed where they
// are read, as untitled.stream adds with one "+" where the library is.
export function TodayBoard({ data, user, day, today, onDay }: Props) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(user?.topics ?? []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  useEffect(() => { setSelected(user?.topics ?? []); }, [user]);
  async function saveTopics() {
    setBusy(true);
    setNote("");
    try {
      await api<{ user: User }>("preferences", { topics: selected });
      window.location.reload();
    } catch (e) {
      setNote((e as Error).message);
      setBusy(false);
    }
  }
  // DECISION(2026-10-26, Anastasia/Claude Code; Yelysei's review of PR #27): sections come from the user's own
  // topics, not from data.topics ∩ user.topics, so a followed topic missing from the snapshot's list and a
  // `requested:<key>` entry still get a section ("Waiting for its first brief"); the legacy id `ukraine-aid` maps
  // to `russia-ukraine-war` (DECISIONS › User account and interface item 2).
  const followedIds = Array.from(new Set((user?.topics ?? []).map((id) => (id === "ukraine-aid" ? "russia-ukraine-war" : id))));
  const catalog = new Map((data?.topics ?? []).map((t) => [t.id, t]));
  const topics = followedIds.map((id) => {
    const known = catalog.get(id);
    if (known) return { topic: known, waitingFirst: false };
    const requested = id.startsWith("requested:");
    return { topic: { id, name: requested ? id.slice("requested:".length) : id } as Topic, waitingFirst: true };
  });
  const stories = visibleStories(data?.events ?? [], day, "", followedIds);
  const status = data?.status ?? "pending";
  const noEdition = data?.publication?.status === "pending"; // per date: nothing installed for this day
  const { cut, passed, hoursUntil } = describeCut(day);
  const isToday = day === today;
  const isPast = day < today;
  const n = topics.length;

  return (
    <div className="tb">
      <header className="tb-head">
        <div>
          <h1>
            {isToday ? "Today" : "Edition"}, <span className="tb-date">{longDate(day)}</span>
          </h1>
          <p className="tb-meta">
            <span className="tb-count">{`${n} ${n === 1 ? "topic" : "topics"} in your brief`}</span>
            {noEdition && (
              <span className="tb-status">
                {`No edition for ${longDate(day)} is installed on this portal. No published events are available for this edition.`}
              </span>
            )}
            {!noEdition && status !== "demo" && stories.length === 0 && (
              <span className="tb-status">No published events are available for this edition.</span>
            )}
          </p>
        </div>
        <div className="tb-controls">
          <EditionNavigation day={day} today={today} onDay={onDay} />
          <button type="button" className="tb-add" aria-expanded={open || n === 0} aria-controls="tb-topics" onClick={() => setOpen((o) => !o)}>
            <span className="tb-add-mark" aria-hidden="true">{open || n === 0 ? "−" : "+"}</span>
            {n === 0 ? "Choose topics" : "Add topics"}
          </button>
        </div>
      </header>

      {/* The picker stays in the document while closed (hidden), so the page keeps one place for topics. */}
      <section id="tb-topics" className="tb-topics" aria-label="Your topics" hidden={!open && n > 0}>
        <TopicPicker
          topics={data?.topics ?? []}
          catalogRevision={data?.catalog_revision ?? null}
          selected={selected}
          onChange={setSelected}
          busy={busy}
          onSave={saveTopics}
          saveLabel="Save topics"
          compact
        />
        {note && (
          <p className="message" role="status">
            {note}
          </p>
        )}
      </section>

      {topics.map(({ topic: t, waitingFirst }, i) => {
        const own = stories.filter((e) => e.topic_id === t.id);
        const edition = data?.editions?.find((e) => e.topic_id === t.id && e.date === day);
        const quiet = !!(data && edition && isQuietDay(data, edition));
        const below = roundupCount(edition);
        const meta = waitingFirst
          ? "Waiting for its first brief"
          : quiet
            ? "No story crossed the bar today"
            : own.length
              ? `${own.length} ${own.length === 1 ? "story" : "stories"} today`
              : edition
                // An installed edition that is neither quiet nor carrying a visible story says so; "no edition"
                // and "waiting" are only for topics without an edition row (Yelysei's re-review of PR #27).
                ? edition.completion === "partial"
                  ? "Partial edition"
                  : "No stories in this edition"
                : isPast
                  ? noEdition
                    ? "No edition installed for this date"
                    : "No edition for this topic on this date"
                  : passed
                    ? "Waiting for the edition"
                    // DECISION(2026-10-27, Anastasia/Claude Code): the countdown names the data cutoff ("Data cutoff in
                    // 3 hours"), never a bare "Cut in", and the waiting card says it is not a publication time. Why:
                    // Vadim read "Cut in 3 hours" as a promise that the edition appears then (Issue #2, comment
                    // 6436182315); the number is ceil(hours until 05:30 New York), the end of data collection; the
                    // run, the dump and the installation follow on the team's machines, with no time this page can know.
                    : `Data cutoff in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`;
        return (
          <section key={t.id} className={`tb-section tb-tint-${(i % 4) + 1}`} aria-labelledby={`tb-${t.id}`}>
            <div className="tb-section-head">
              <h2 id={`tb-${t.id}`}>
                <Link href={`/topics/${encodeURIComponent(t.id)}?date=${day}`}>{t.name}</Link>
              </h2>
              <p className="tb-section-meta">{meta}</p>
            </div>
            <ul className="tb-row" role="list" aria-label={`${t.name}: stories of the ${day} edition`}>
              {own.map((e, k) => (
                <StoryCard key={e.id} event={e} day={day} lead={k === 0} />
              ))}
              {quiet && (
                <li className="tb-card tb-card-quiet">
                  <div className="tb-card-link">
                    <span className="tb-card-topic">{t.name}</span>
                    <h3>No story crossed the bar today.</h3>
                    <p>The roundup carries the day.</p>
                  </div>
                </li>
              )}
              {edition && (
                <li className="tb-card tb-card-roundup">
                  {/* DECISION(2026-10-27, Anastasia/Claude Code): the card leads to this topic's part of the "Also today"
                      section on this page (components/editorial.tsx, anchor also-today-<topic id>), not to the topic page, which
                      carries no roundup since the second cabinet pass; an edition without roundup lines keeps the topic
                      link. Why: Anastasia, 27 October: the card's "12 events below the bar" opened a page without them. */}
                  {below ? (
                    <a href={`#also-today-${encodeURIComponent(t.id)}`} className="tb-card-link">
                      <span className="tb-card-topic">Also today</span>
                      <h3>{`${below} ${below === 1 ? "event" : "events"} below the bar`}</h3>
                      <p>{edition.roundup.map((g) => g.name).filter(Boolean).join(" · ")}</p>
                      {edition.completion === "partial" && <span className="tb-card-meta">partial edition</span>}
                    </a>
                  ) : (
                    <Link href={`/topics/${encodeURIComponent(t.id)}?date=${day}`} className="tb-card-link">
                      <span className="tb-card-topic">Also today</span>
                      <h3>{`${below} events below the bar`}</h3>
                      {edition.completion === "partial" && <span className="tb-card-meta">partial edition</span>}
                    </Link>
                  )}
                </li>
              )}
              {!own.length && !quiet && !edition && (
                <li className="tb-card tb-card-wait">
                  <div className="tb-card-link">
                    <span className="tb-card-topic">{t.name}</span>
                    <h3>{isPast ? "No edition for this topic." : passed ? "Not published yet." : "Not cut yet."}</h3>
                    {/* DECISION(2026-10-26, Anastasia/Claude Code): on a past date a topic without an edition says so; the cut
                        promise ("the team prepares the edition after the cut") is for today only. Why: once other topics
                        of that day are installed, "waiting" would be false for the missing one. */}
                    <p>
                      {isPast
                        ? `Nothing was installed for ${t.name} on ${longDate(day)}.`
                        : `Data cutoff 05:30 New York, ${utcLabel(cut)}${passed ? "" : `, in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`}. A cutoff, not a publication time: the team runs the processing afterwards and installs the edition when it is ready.`}
                    </p>
                  </div>
                </li>
              )}
            </ul>
          </section>
        );
      })}

    </div>
  );
}
