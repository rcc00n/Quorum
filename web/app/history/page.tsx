import { Portal } from "@/components/portal";
import type { Metadata } from "next";
import { validEditionDate } from "@/lib/edition-navigation.mjs";
export const metadata: Metadata = { title: "History" };
export default async function Page({ searchParams }: { searchParams: Promise<{ date?: string; topic?: string }> }) {
  const q = await searchParams;
  return <Portal view="history" initialDay={validEditionDate(q.date) ? q.date : undefined}
    initialTopic={q.topic && /^[a-z0-9][a-z0-9-]{0,63}$/.test(q.topic) ? q.topic : undefined} />;
}
