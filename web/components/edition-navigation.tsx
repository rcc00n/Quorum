"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { shiftEditionDate } from "@/lib/edition-navigation.mjs";
import "@/app/edition-navigation.css";

export function EditionNavigation({ day, today, onDay }: { day: string; today: string; onDay: (day: string) => void }) {
  const previous = shiftEditionDate(day, -1), next = shiftEditionDate(day, 1);
  return <div className="edition-navigation" role="group" aria-label="Browse editions by date">
    <button type="button" aria-label="Previous day" disabled={!previous} onClick={() => previous && onDay(previous)}><ChevronLeft size={18} aria-hidden="true" /></button>
    <label><span>Edition date</span><input type="date" value={day} max={today} onChange={e => { if (e.target.value) onDay(e.target.value); }} /></label>
    <button type="button" aria-label="Next day" disabled={!next || next > today} onClick={() => next && onDay(next)}><ChevronRight size={18} aria-hidden="true" /></button>
    {day !== today && <button type="button" className="edition-today" onClick={() => onDay(today)}>Today</button>}
  </div>;
}
