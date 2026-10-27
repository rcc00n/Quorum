// DECISION(2026-10-27, Anastasia/Claude Code): one notice at the top of every signed-in workspace page (not the first
// setup, which returns earlier and shows no headlines), under the site header and
// above the page title: the headlines are picked and worded by an AI from the articles it reads, so some keep an
// outlet's slant; read them with humour; Quorum supports no party or group; after the hackathon, headlines will be written
// from each story's confirmed facts (a planned change, docs/DECISIONS.md › After the hackathon, fifth item). Not dismissible, so every reader, the jury
// included, sees it on every page. Plain text with role="note", no icon carries meaning. The only yellow in the
// identity (`--notice-yellow`, web/DESIGN.md › Color and › Components). Why: Anastasia, 2026-10-27: some headlines in
// today's editions read one-sided or provocative; the pipeline stays as it is today, the page says so plainly.
// Canonical: docs/DECISIONS.md › User account and interface, item 12.
export const AI_NOTICE_TITLE = "AI-written headlines.";
export const AI_NOTICE_TEXT =
  "An AI picks and words these headlines from the articles it reads, so some keep an outlet's slant: take them with a sense of humour. Quorum supports no political party or group. After the hackathon, headlines will be written from each story's confirmed facts, not from the articles' headlines.";

export function AiNotice() {
  return (
    <p className="ai-notice" role="note">
      <strong>{AI_NOTICE_TITLE}</strong> {AI_NOTICE_TEXT}
    </p>
  );
}
