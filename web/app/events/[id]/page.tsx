import { Portal } from "@/components/portal";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const p = await params;
  const q = await searchParams;
  return (
    <Portal
      view="event"
      id={p.id}
      initialDay={
        q.date && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : undefined
      }
    />
  );
}
