import { Portal } from "@/components/portal";
import type { Metadata } from "next";
import { validEditionDate } from "@/lib/edition-navigation.mjs";
export const metadata: Metadata = { title: "Today" };
export default async function Page({searchParams}: {searchParams: Promise<{date?: string}>}) {
  const q = await searchParams;
  return <Portal view="dashboard" initialDay={validEditionDate(q.date) ? q.date : undefined} />;
}
