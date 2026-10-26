"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight,
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  Bookmark,
  ArrowRight,
  RefreshCw,
  FileSearch,
} from "lucide-react";
import { Spectrum } from "./spectrum";
import { EditionNotes } from "./editorial";
import { visibleStories, isQuietDay } from "@/lib/editorial";
import { AnalysisWorkspace, PublicationNotice } from "./analysis-workspace";
import type { Publication } from "@/lib/analysis";
import { Brand } from "./brand";
import { TopicPicker, FirstSetup } from "./topic-picker";
import { BriefStatus } from "./brief-status";
import { TodayBoard } from "./today-board";
import { StoryCrumb, Story, storyReadable } from "./story";
import {
  api,
  session,
  feed,
  eventSnapshot,
  previewSnapshot,
  User,
  Snapshot,
  Event,
  Source,
  rating,
  cohort,
  safeUrl,
} from "@/lib/api";
const today = () => new Date().toLocaleDateString("en-CA");
function Empty({
  title = "Your next perspective is on its way",
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <FileSearch size={34} strokeWidth={1} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Analysis({
  event,
  publication,
  sources,
}: {
  event: Event;
  publication?: Publication;
  sources: Source[];
}) {
  if (event.analysis)
    return (
      <AnalysisWorkspace
        event={event}
        publication={publication}
        sources={sources}
      />
    );
  // The story layout also on the claims-only page when the reasoning story carries a readable article
  // (components/story.tsx); the claim sections below become its appendix.
  const readable = storyReadable(event, sources);
  return (
    <div className={readable ? "story-page story-page-plain" : undefined}>
      {readable ? (
        <Story event={event} sources={sources} />
      ) : (
        <>
          <p className="eyebrow">EVENT ANALYSIS / {event.date}</p>
          <h1>{event.title}</h1>
          <p className="lede">{event.summary}</p>
          {event.importance && (
            <aside className="notice">
              <strong>{event.importance.label}</strong>
              <p>{event.importance.explanation}</p>
            </aside>
          )}
        </>
      )}
      {(
        [
          "established",
          "statements",
          "disputed",
          "unknown",
          "coverage",
        ] as const
      ).map((key, i) => (
        <section className="analysis-section" id={`claims-${key}`} key={key}>
          <p className="eyebrow">0{i + 1}</p>
          <h2>
            {
              [
                "What is established",
                "Attributed statements",
                "Disputed claims",
                "What remains unknown",
                "Coverage differences",
              ][i]
            }
          </h2>
          {event[key].length ? (
            event[key].map((item, j) => (
              <article key={j}>
                <h3>{item.text}</h3>
                <p>{item.explanation}</p>
                {item.sources.map(
                  (s, k) =>
                    safeUrl(s.url) && (
                      <a
                        key={k}
                        className="source-link"
                        href={safeUrl(s.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {s.title}
                        <ArrowUpRight size={14} />
                      </a>
                    ),
                )}
              </article>
            ))
          ) : (
            <p className="muted">No information supplied for this section.</p>
          )}
        </section>
      ))}
      <Spectrum sources={event.sources} />
      <AnalysisWorkspace
        event={event}
        publication={publication}
        sources={sources}
        supplementary
      />
    </div>
  );
}
export function Portal({
  view,
  id,
  initialDay,
  initialRevision,
  initialPreview = false,
}: {
  view: string;
  id?: string;
  initialDay?: string;
  initialRevision?: string;
  initialPreview?: boolean;
}) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [day, setDay] = useState(initialDay || today());
  const [topic, setTopic] = useState(view === "topic" ? id || "" : "");
  const [selected, setSelected] = useState<string[]>([]);
  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const s = await session();
      if (!s.user) {
        router.replace("/login");
        return;
      }
      setUser(s.user);
      setSelected(s.user.topics);
      setData(
        view === "event"
          ? initialPreview
            ? await previewSnapshot(initialDay)
            : await eventSnapshot(id || "", initialDay, initialRevision)
          : await feed(day, topic),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [router, day, topic, view, id, initialDay, initialRevision, initialPreview]);
  useEffect(() => {
    void load();
  }, [load]);
  async function saveTopics() {
    setBusy(true);
    setMessage("");
    try {
      const s = await api<{ user: User }>("preferences", { topics: selected });
      setUser(s.user);
      setMessage("Topics saved.");
      if (view === "onboarding") router.push("/dashboard");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveForm(e: React.FormEvent<HTMLFormElement>, target: string) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api(target, Object.fromEntries(new FormData(e.currentTarget)));
      setMessage(target === "profile" ? "Profile saved." : "Password changed.");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function signout() {
    try {
      await api("logout", {});
      router.replace("/login");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const digests = (data?.digests || []).filter((d) =>
    view === "history"
      ? d.date === day && (!topic || d.topic_id === topic)
      : user?.topics.includes(d.topic_id),
  );
  const names: Record<string, string> = {
    dashboard: "Your daily perspective",
    topic: data?.topics.find((t) => t.id === id)?.name || "Topic brief",
    history: "The perspective archive",
    settings: "Your workspace",
    onboarding: "What matters to you?",
    event: "Event analysis",
  };
  const topicsPanel = (
    <TopicPicker
      topics={data?.topics ?? []}
      catalogRevision={data?.catalog_revision ?? null}
      selected={selected}
      onChange={setSelected}
      busy={busy}
      onSave={saveTopics}
      saveLabel={view === "onboarding" ? "Continue to your brief" : "Save topics"}
    />
  );
  // DECISION(2026-10-26, Anastasia/Claude Code): first setup is its own full screen (the prototype's night
  // screen), not a page inside the workspace layout; the session, catalog and preferences logic above is
  // unchanged. Why: WEB-UX-02; the API and the workspace stay Vadim's.
  if (view === "onboarding") {
    return (
      <FirstSetup loading={loading} error={error} onRetry={load} message={message} demo={data?.status === "demo"}>
        {topicsPanel}
      </FirstSetup>
    );
  }
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <Brand />
        <p className="nav-label">YOUR WORKSPACE</p>
        <nav>
          {[
            // DECISION(2026-10-26, Anastasia/Claude Code): the menu reads Today · History · My topics and sits
            // in the top bar (styled by app/workspace.css); settings stay behind "My topics". Why: Anastasia's
            // brief for the personal page.
            [LayoutDashboard, "Today", "/dashboard"],
            [History, "History", "/history"],
            [Settings, "My topics", "/settings"],
          ].map(([Icon, label, url]) => {
            const I = Icon as typeof History;
            return (
              <Link
                key={url as string}
                className={path === url ? "active" : ""}
                href={url as string}
              >
                <I size={18} />
                {label as string}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-topics">
          <p className="nav-label">FOLLOWING</p>
          {data?.topics
            .filter((t) => user?.topics.includes(t.id))
            .map((t) => (
              <Link key={t.id} href={"/topics/" + t.id}>
                <Bookmark size={15} />
                {t.name}
              </Link>
            ))}
          {!user?.topics.length && (
            <p className="help">Your interests belong here.</p>
          )}
          <Link className="manage-topics" href="/onboarding">
            Choose topics <ArrowUpRight size={14} />
          </Link>
        </div>
        <div className="sidebar-bottom">
          {user?.is_staff && <a href="/staff/">Quorum Control ↗</a>}
          <p className="account-name">
            {user?.name || user?.username || "Your account"}
          </p>
          <button className="text-button" onClick={signout}>
            <LogOut size={15} />
            Sign out
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <span>THE QUORUM BRIEF</span>
          <span>
            {new Intl.DateTimeFormat("en", {
              month: "long",
              day: "numeric",
              year: "numeric",
            }).format(new Date())}
          </span>
        </header>
        <main id="main" className="workspace-main">
          {loading ? (
            <div className="loading" role="status">
              <div className="loading-line" />
              <h1>Preparing your workspace…</h1>
            </div>
          ) : error ? (
            <div className="empty" role="alert">
              <h1>We couldn’t load your workspace.</h1>
              <p>{error}</p>
              <button className="button" onClick={load}>
                <RefreshCw size={16} />
                Try again
              </button>
            </div>
          ) : (
            <>
              {view === "event" ? (
                // The story page's navigation: the topic's name, back to its page (components/story.tsx).
                <StoryCrumb
                  topic={data?.topics.find((t) => t.id === data?.events.find((e) => e.id === id)?.topic_id) ?? null}
                  date={data?.events.find((e) => e.id === id)?.date ?? initialDay}
                />
              ) : view !== "dashboard" && (
              <div className="page-heading">
                <p className="eyebrow">
                  {view === "dashboard"
                    ? "CURATED AROUND YOUR INTERESTS"
                    : view.toUpperCase()}
                </p>
                {view !== "event" && <h1>{names[view]}</h1>}
                <p>
                  {view === "dashboard"
                    ? "A considered view of the stories that matter to you."
                    : view === "history"
                      ? "Return to a day. Revisit the evidence."
                      : view === "settings"
                        ? "A few details. A more personal brief."
                        : view === "onboarding"
                          ? "Start with your interests. Keep an open perspective."
                          : ""}
                </p>
              </div>
              )}
              {data?.status === "demo" && (
                <p className="message" role="status">
                  DEMO · Fictional interface fixture. Not verified news or live
                  findings.
                </p>
              )}
              <PublicationNotice publication={data?.publication} />
              {message && (
                <p className="message" role="status">
                  {message}
                </p>
              )}
              {view === "settings" ? (
                <div className="settings-grid">
                  <section>
                    <h2>Profile</h2>
                    <form onSubmit={(e) => saveForm(e, "profile")}>
                      <label>
                        Name
                        <input
                          name="name"
                          defaultValue={user?.name}
                          maxLength={150}
                          autoComplete="name"
                        />
                      </label>
                      <label>
                        Email
                        <input
                          name="email"
                          type="email"
                          defaultValue={user?.email}
                          autoComplete="email"
                        />
                      </label>
                      <button disabled={busy} className="button">
                        Save profile
                      </button>
                    </form>
                  </section>
                  {topicsPanel}
                  <section>
                    <h2>Change password</h2>
                    <form onSubmit={(e) => saveForm(e, "password")}>
                      <label>
                        Current password
                        <input
                          name="old_password"
                          type="password"
                          autoComplete="current-password"
                          required
                        />
                      </label>
                      <label>
                        New password
                        <input
                          name="new_password1"
                          type="password"
                          autoComplete="new-password"
                          required
                          minLength={8}
                        />
                      </label>
                      <label>
                        Confirm new password
                        <input
                          name="new_password2"
                          type="password"
                          autoComplete="new-password"
                          required
                          minLength={8}
                        />
                      </label>
                      <button disabled={busy} className="button">
                        Change password
                      </button>
                    </form>
                  </section>
                  <section>
                    <h2>End your session</h2>
                    <button className="secondary-button" onClick={signout}>
                      Sign out <LogOut size={16} />
                    </button>
                  </section>
                </div>
              ) : view === "onboarding" ? (
                topicsPanel
              ) : view === "dashboard" ? (
                // DECISION(2026-10-26, Anastasia/Claude Code; Yelysei's review of PR #27): the board keeps the honest
                // empty states and the edition notes of the brief view; a failed, stale or partial edition never
                // reads as "waiting" (DECISIONS › User account and interface, Guards).
                data?.status === "error" || data?.publication?.status === "error" ? (
                  <Empty title="This edition is unavailable">
                    A data or processing failure prevented this edition from loading. No completed quiet day is
                    inferred.
                  </Empty>
                ) : data?.publication?.status === "stale" ? (
                  <Empty title="This stored edition is out of date">
                    No stories are available in this stored edition. A current result has not been supplied.
                  </Empty>
                ) : data?.publication?.status === "partial" ? (
                  <Empty title="This edition is incomplete">
                    No completed major-story selection was supplied. Further results may still be missing.
                  </Empty>
                ) : (
                  <>
                    <TodayBoard data={data} user={user} day={day} today={today()} onDay={(d) => setDay(d)} />
                    {data && <EditionNotes snapshot={data} day={day} topic="" followed={user?.topics || []} />}
                  </>
                )
              ) : view === "event" ? (
                (() => {
                  const event = data?.events.find((e) => e.id === id);
                  return event ? (
                    <Analysis
                      event={event}
                      publication={data?.publication}
                      sources={data?.sources || event.sources}
                    />
                  ) : (
                    <Empty title="This analysis is not available">
                      No published analysis is available for this event.
                      Conclusions and evidence will appear here when supplied.
                      <br />
                      <Link href="/dashboard">
                        Return to your daily brief →
                      </Link>
                    </Empty>
                  );
                })()
              ) : (
                <>
                  <div className="brief-toolbar">
                    <div className="tabs">
                      <span className="selected">
                        {view === "history"
                          ? "Past digests"
                          : "The daily edition"}
                      </span>
                      <span>Evidence first</span>
                    </div>
                    <div className="filters">
                      <label>
                        Edition date
                        <input
                          type="date"
                          value={day}
                          max={today()}
                          onChange={(e) => setDay(e.target.value || today())}
                        />
                      </label>
                      {view === "history" && (
                        <label>
                          Topic
                          <select
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                          >
                            <option value="">All topics</option>
                            {data?.topics.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                    </div>
                  </div>
                  {view === "dashboard" && (
                    <div className="followed">
                      <Bookmark size={16} />
                      <span>
                        {user?.topics.length
                          ? `${user.topics.length} ${user.topics.length === 1 ? "topic" : "topics"} in your brief`
                          : "Make this brief your own"}
                      </span>
                      <Link href="/onboarding">
                        Choose topics <ArrowUpRight size={14} />
                      </Link>
                    </div>
                  )}
                  <div className="brief-columns">
                    <section>
                      <div className="section-heading">
                        <h2>
                          {view === "history"
                            ? "Daily digests"
                            : view === "topic"
                              ? "Important stories"
                              : "Today’s important stories"}
                        </h2>
                        <span className="edition-label">{day}</span>
                      </div>
                      {view === "history" ? (
                        digests.length ? (
                          digests.map((d, i) => (
                            <article className="event-row" key={i}>
                              <p className="eyebrow">DIGEST / {d.date}</p>
                              <h3>
                                <Link
                                  href={`/topics/${d.topic_id}?date=${d.date}`}
                                >
                                  {data?.topics.find((t) => t.id === d.topic_id)
                                    ?.name || d.topic_id}
                                </Link>
                              </h3>
                              <p>{d.summary}</p>
                            </article>
                          ))
                        ) : (
                          <Empty title="An archive begins with the first brief">
                            No digests are available for this date and topic.
                            Choose another edition or return when your first
                            digest is published.
                          </Empty>
                        )
                      ) : (
                        (() => {
                          const events = visibleStories(
                            data?.events || [],
                            day,
                            topic,
                            user?.topics || [],
                          );
                          const quiet = !!data?.editions?.some(
                            (e) =>
                              e.date === day &&
                              (topic
                                ? e.topic_id === topic
                                : !!user?.topics.includes(e.topic_id)) &&
                              isQuietDay(data, e),
                          );
                          return events.length ? (
                            events.map((e, i) => (
                              <article className="event-row" key={e.id}>
                                <p className="eyebrow">
                                  {String(i + 1).padStart(2, "0")} /{" "}
                                  {e.importance?.label ||
                                    "Importance not supplied"}
                                </p>
                                <h3>
                                  <Link
                                    href={"/events/" + e.id + "?date=" + day}
                                  >
                                    {e.title} <ArrowUpRight size={19} />
                                  </Link>
                                </h3>
                                <p>{e.summary}</p>
                                {e.importance && (
                                  <p className="help">
                                    {e.importance.explanation}
                                  </p>
                                )}
                              </article>
                            ))
                          ) : quiet ? null : data?.status === "error" ||
                            data?.publication?.status === "error" ? (
                            <Empty title="This edition is unavailable">
                              A data or processing failure prevented this
                              edition from loading. No completed quiet day is
                              inferred.
                            </Empty>
                          ) : data?.publication?.status === "stale" ? (
                            <Empty title="This stored edition is out of date">
                              No stories are available in this stored edition. A
                              current result has not been supplied.
                            </Empty>
                          ) : data?.publication?.status === "partial" ? (
                            <Empty title="This edition is incomplete">
                              No completed major-story selection was supplied.
                              Further results may still be missing.
                            </Empty>
                          ) : (
                            // DECISION(2026-10-26, Anastasia/Claude Code): the empty brief explains the edition cut and what
                            // happens next instead of a placeholder (WEB-UX-03; see brief-status.tsx). Why: DECISIONS › User
                            // account and interface item 10.
                            <BriefStatus
                              day={day}
                              topic={topic}
                              topics={data?.topics || []}
                              followed={user?.topics || []}
                              status={data?.status}
                              publicationStatus={data?.publication?.status}
                              today={today()}
                            />
                          );
                        })()
                      )}
                      {data && view !== "history" && (
                        <EditionNotes
                          snapshot={data}
                          day={day}
                          topic={topic}
                          followed={user?.topics || []}
                        />
                      )}
                    </section>
                    <aside className="brief-aside">
                      <p className="eyebrow">THE READING ROOM</p>
                      <h3>Understanding takes perspective.</h3>
                      <p>
                        Every brief separates established facts, attributed
                        statements and what remains uncertain.
                      </p>
                      <div className="aside-rule" />
                      <h4>Latest digest</h4>
                      {digests[0] ? (
                        <p>{digests[0].summary}</p>
                      ) : (
                        <p>
                          Your latest digest will appear here when published.
                        </p>
                      )}
                      <Link href="/history">
                        Explore the archive <ArrowRight size={15} />
                      </Link>
                      <div className="aside-rule" />
                      <span className="status-dot" />
                      <span className="help">
                        {data?.status === "pending"
                          ? "Live data connection pending"
                          : data?.status === "demo"
                            ? "DEMO fixture · fictional data"
                            : data?.status === "error"
                              ? "Data unavailable"
                              : "Source data supplied"}
                      </span>
                    </aside>
                  </div>
                  {view === "topic" && (
                    <Spectrum sources={data?.sources || []} />
                  )}
                </>
              )}
            </>
          )}
        </main>
        <footer className="workspace-footer">
          <span>QUORUM</span>
          <span>Follow the evidence. Keep the questions.</span>
        </footer>
      </div>
    </div>
  );
}
