// The edition cut: 05:30 America/New_York on the edition's date (docs/DECISIONS.md › Daily editions for users:
// 09:30Z until the end of daylight saving on 2026-11-01, 10:30Z after, converted per date in code).
// DECISION(2026-10-26, Anastasia/Claude Code): the cut is computed per date from the New York clock through
// Intl, never from a fixed UTC offset, and the page only ever says when the cut is or was; it never promises
// when an edition will be published, because the run is started by the team after the cut and the web app
// starts nothing. Plain ESM so the same code runs in the browser and in `node web/tests/edition-cut.cjs`.
const NEW_YORK = "America/New_York";

function newYorkParts(date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: NEW_YORK,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(date);
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour), minute: Number(p.minute) };
}

/** The UTC instant of 05:30 New York on an edition date given as YYYY-MM-DD. */
export function cutUtc(editionDate) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(editionDate));
  if (!m) throw new Error("edition date must be YYYY-MM-DD");
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  for (const hour of [9, 10, 8, 11]) {
    const candidate = new Date(Date.UTC(y, mo - 1, d, hour, 30));
    const ny = newYorkParts(candidate);
    if (ny.date === editionDate && ny.hour === 5 && ny.minute === 30) return candidate;
  }
  throw new Error("no 05:30 New York on " + editionDate);
}

/** Where a viewer stands relative to an edition's cut. */
export function describeCut(editionDate, now = new Date()) {
  const cut = cutUtc(editionDate);
  const ms = cut.getTime() - now.getTime();
  return { cut, passed: ms <= 0, hoursUntil: ms > 0 ? Math.ceil(ms / 3_600_000) : 0 };
}

export function utcLabel(date) {
  return date.toISOString().slice(11, 16) + " UTC";
}

/** The viewer's own clock for the same instant, with the zone named, or null when the environment cannot say. */
export function localLabel(date) {
  try {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(date);
  } catch {
    return null;
  }
}
