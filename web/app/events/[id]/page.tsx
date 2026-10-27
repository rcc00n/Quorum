import { Portal } from "@/components/portal";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "Story" };
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ date?: string; revision?: string; preview?: string }>;
}) {
  const p = await params;
  const q = await searchParams;
  return (
    <Portal
      view="event"
      id={p.id}
      initialRevision={
        q.revision && /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(q.revision)
          ? q.revision
          : undefined
      }
      initialDay={
        q.date && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : undefined
      }
      initialPreview={q.preview === "1"}
    />
  );
}
