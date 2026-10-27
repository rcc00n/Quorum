import { Portal } from "@/components/portal";
export default async function Page({searchParams}: {searchParams: Promise<{date?: string}>}) {
  const q = await searchParams;
  return <Portal view="dashboard" initialDay={q.date && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : undefined} />;
}
