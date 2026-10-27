export function validEditionDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function shiftEditionDate(day, offset) {
  if (!validEditionDate(day)) return null;
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  const next = date.toISOString().slice(0, 10);
  return validEditionDate(next) ? next : null;
}

export function editionHref(path, day, topic = "") {
  const query = new URLSearchParams({ date: day });
  if (topic) query.set("topic", topic);
  return `${path}?${query}`;
}
