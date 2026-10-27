import { Portal } from "@/components/portal";
import type { Metadata } from "next";
import { validEditionDate } from "@/lib/edition-navigation.mjs";
export const metadata: Metadata = { title: "Topic" };
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const p = await params;
  const q = await searchParams;
  return (
    <Portal
      view="topic"
      id={p.slug}
      initialDay={
        validEditionDate(q.date) ? q.date : undefined
      }
    />
  );
}
