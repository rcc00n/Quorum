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
  now?: Date;
};

function longDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

export function BriefStatus({ day, topic, topics, followed, status, now }: Props) {
  const { cut, passed, hoursUntil } = describeCut(day, now);
  const local = localLabel(cut);
  const waiting = (topics as TopicProgress[]).filter((t) => (topic ? t.id === topic : followed.includes(t.id)));
  const date = longDate(day);
  return (
    <section className="bs" aria-labelledby="bs-title">
      <p className="bs-kicker">{`Edition ${day} · ${topic ? "one topic" : `${waiting.length} ${waiting.length === 1 ? "topic" : "topics"} in your brief`}`}</p>
      <h3 id="bs-title">{passed ? `The ${date} edition is not published yet.` : `The ${date} edition has not been cut yet.`}</h3>
      <p className="bs-lead">No published events are available for this edition.</p>
      <dl className="bs-facts">
        <dt>Edition cut</dt>
        <dd>
          {`05:30 New York · ${utcLabel(cut)}${local ? ` · ${local} on your clock` : ""} · ${passed ? "passed" : `in ${hoursUntil} ${hoursUntil === 1 ? "hour" : "hours"}`}`}
        </dd>
        <dt>Then</dt>
        <dd>
          The team starts one run per topic after the cut. The edition appears here when it is published; nothing
          is started from this page.
        </dd>
        {status === "pending" && (
          <>
            <dt>This portal</dt>
            <dd>No editions have been published to it yet.</dd>
          </>
        )}
      </dl>
      {waiting.length === 0 && !topic && (
        <p className="bs-none">
          You follow no topics yet. <Link href="/onboarding">Choose your topics</Link> and the next edition will be
          prepared for them.
        </p>
      )}
      {waiting.length > 0 && (
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
