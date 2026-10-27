"use client";
import { Children, cloneElement, isValidElement, useState } from "react";
import type { ReactElement, ReactNode } from "react";

// DECISION(2026-10-27, Anastasia/Claude Code; cabinet pass): a status group of "Also today" shows three
// events; from the fourth on they wait behind one "Show N more" button, and the third event is cut and fades
// under the button so the reader sees the list continues. Every item stays in the document (hidden, not
// removed), so counts and assistive navigation see the whole group; "Show fewer" folds it back. Why:
// Anastasia's review of 2026-10-27: a group of nineteen single-source lines made the section a wall.
export function RoundupGroup({ name, children, limit = 3 }: { name: string; children: ReactNode; limit?: number }) {
  const [open, setOpen] = useState(false);
  const items = Children.toArray(children).filter(isValidElement) as ReactElement<{ hidden?: boolean }>[];
  const more = items.length - limit;
  const collapsed = more > 0 && !open;
  return (
    <div className="roundup-group" data-collapsed={collapsed ? "true" : undefined}>
      <h4>{name}</h4>
      {items.map((item, i) => (collapsed && i >= limit ? cloneElement(item, { hidden: true }) : item))}
      {more > 0 && (
        <button type="button" className="roundup-more" aria-expanded={!collapsed} onClick={() => setOpen((o) => !o)}>
          {collapsed ? `Show ${more} more` : "Show fewer"}
        </button>
      )}
    </div>
  );
}
