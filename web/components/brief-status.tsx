"use client";
import Link from "next/link";
import type { Topic } from "@/lib/api";
import { describeCut, localLabel, utcLabel } from "@/lib/edition-cut.mjs";
import "@/app/brief-status.css";

// DECISION(2026-10-26, Anastasia/Claude Code): the waiting state says only what the system does and what the
// data shows: which edition is viewed, when its 05:30 New York cut is or was (computed per date), that the
// team starts one run per topic after the cut and the edition appears here when published, and which topics
// wait. It never promises a publication time (the web app starts nothing; DECISIONS › Daily editions) and it
// never shows a placeholder count: "collecting since" and "publications so far" render only when the
// snapshot carries them (it does not today; a topic-progress field is proposed to the owners in Issue #2).
// The sentence "No published events are available for this edition." stays for web/tests/browser.cjs.
// Wording is Yelysei's to approve (DECISIONS › User account and interface item 10).

type TopicProgress = Topic & { created_at?: string | null; documents_in_window?: number | null };

type Props = {
  day: string;
  topic: string;
  topics: Topic[];
  followed: string[];
  status?: string;
  /** publication.status of the viewed date: "pending" = no edition installed for that date (per-date, not portal-wide). */
  publicationStatus?: string;
  /** Today's date (YYYY-MM-DD) to tell a past date, for which no run will be started, from today's. */
  today?: string;
  now?: Date;
};

function longDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

export function BriefStatus({ day, topic, topics, followed, status, publicationStatus, today, now }: Props) {
  const { cut, passed, hoursUntil } = describeCut(day, now);
  const local = localLabel(cut);
  const waiting = (topics as TopicProgress[]).filter((t) => (topic ? t.id === topic : followed.includes(t.id)));
  const date = longDate(day);
  // DECISION(2026-10-26, Anastasia/Claude Code; Yelysei's review of PR #25): the next-step copy is shown only when
  // no edition is installed for the viewed date (publication.status "pending" is per date, never portal-wide); an
  // installed edition with no stories for the topic says so; a past date without an edition promises no run.
  const installed = publicationStatus !== undefined && publicationStatus !== "pending";
  const past = !!today && day < today;
  const heading = installed
    ? `The ${date} edition is installed, with no stories for ${topic ? "this topic" : "your topics"}.`
    : past
      ? `No edition for ${date} is installed on this portal.`
      : passed
        ? `The ${date} edition is not published yet.`
        : `The ${date} edition has not been cut yet.`;
  const nextStep = !installed && !past;
  void status;
  return (
    <section className="bs" aria-labelledby="bs-title">
      <p className="bs-kicker">{`Edition ${day} · ${topic ? "one topic" : `${waiting.length} ${waiting.length === 1 ? "topic" : "topics"} in your brief`}`}</p>
      <h3 id="bs-title">{heading}</h3>
      <p className="bs-lead">No published events are available for this edition.</p>
      {nextStep && (
        <dl className="bs-facts">
          {/* "Data cutoff", not "Edition cut": see the DECISION in today-board.tsx (Vadim's reading of 2026-10-27). */}
          <dt>Data cutoff</dt>
          <dd>
            {`05:30 New York · ${utcLabel(cut)}${local ? ` · ${local} on your clock` : ""} · ${passed ? "passed" : `in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`}`}
          </dd>
          <dt>Then</dt>
          <dd>
            After the cut, the team starts one run for each topic it prepares that day, on its own machine. When a
            run is finished, the deploy owner installs its edition on this site and it appears here. Nothing is
            started from this page, so it cannot say when that will be.
          </dd>
        </dl>
      )}
      {waiting.length === 0 && !topic && (
        <p className="bs-none">
          You follow no topics yet. <Link href="/onboarding">Choose your topics</Link>; their briefs appear here once
          an installed edition covers them.
        </p>
      )}
      {nextStep && waiting.length > 0 && (
        <ul className="bs-topics" role="list" aria-label="Topics waiting for this edition">
          {waiting.map((t) => (
            <li key={t.id}>
              <span className="bs-topic">{t.name}</span>
              <span className="bs-wait">
                {[
                  `waiting for the ${day} edition`,
                  t.created_at ? `collecting since ${String(t.created_at).slice(0, 10)}` : null,
                  typeof t.documents_in_window === "number" ? `${t.documents_in_window} ${t.documents_in_window === 1 ? "publication" : "publications"} so far` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="bs-fine">
        New topics start thin: feeds keep only their latest items, so a topic added today rests on few documents
        until they accumulate. A day with no story above the bar is shown as such, never filled.
      </p>
    </section>
  );
}
