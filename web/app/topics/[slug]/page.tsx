import { Portal } from "@/components/portal";
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
        q.date && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : undefined
      }
    />
  );
}
