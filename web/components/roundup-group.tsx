"use client";
import { Children, cloneElement, isValidElement, useState } from "react";
import type { ReactElement, ReactNode } from "react";

// DECISION(2026-10-27, Anastasia/Claude Code; cabinet pass): a status group of "Also today" shows three
// events; from the fourth on they wait behind one "Show N more" button, and the third event is cut and fades
// under the button so the reader sees the list continues. Every item stays in the document (hidden, not
// removed), so counts and assistive navigation see the whole group; "Show fewer" folds it back. Why:
// Anastasia's review of 2026-10-27: a group of nineteen single-source lines made the section a wall.
// DECISION(2026-10-27, Anastasia/Claude Code; Vadim's keyboard finding on PR #62, comment 6436653148): while the
// group is folded, the cut third row is `inert`, so its event and source links are neither tabbable nor read while
// the row is unreadable, and "Show N more" counts that row as not yet shown; the rows from the fourth on are
// `hidden`. Anastasia kept the cut-and-fade teaser over a fully readable third row. Why: keyboard focus must never
// land in clipped content before the button; a teaser that cannot be read should not be operable.
export function RoundupGroup({ name, children, limit = 3 }: { name: string; children: ReactNode; limit?: number }) {
  const [open, setOpen] = useState(false);
  const items = Children.toArray(children).filter(isValidElement) as ReactElement<{ hidden?: boolean; inert?: boolean }>[];
  const collapsed = items.length > limit && !open;
  const unseen = items.length - (limit - 1);
  return (
    <div className="roundup-group" data-collapsed={collapsed ? "true" : undefined}>
      {/* h5 under the topic's h4 in Home's single "Also today" section (2026-10-27). */}
      <h5>{name}</h5>
      {items.map((item, i) =>
        collapsed && i >= limit ? cloneElement(item, { hidden: true }) : collapsed && i === limit - 1 ? cloneElement(item, { inert: true }) : item,
      )}
      {items.length > limit && (
        <button type="button" className="roundup-more" aria-expanded={!collapsed} onClick={() => setOpen((o) => !o)}>
          {collapsed ? `Show ${unseen} more` : "Show fewer"}
        </button>
      )}
    </div>
  );
}
