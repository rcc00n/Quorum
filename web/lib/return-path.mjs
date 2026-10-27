// DECISION(2026-10-27, rcc00n/Codex): accept only local reader/workspace routes after sign-in.
// Why: preserve edition/revision/hash deep links without permitting an external or auth-loop redirect.
export function workspaceReturnPath(value) {
  if (typeof value !== "string" || value.length > 2048 || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return "/dashboard";
  const url = new URL(value, "https://quorum.invalid");
  if (url.origin !== "https://quorum.invalid" || !/^\/(dashboard|history|sources|settings|onboarding|topics\/[^/]+|events\/[^/]+)$/.test(url.pathname)) return "/dashboard";
  return `${url.pathname}${url.search}${url.hash}`;
}
