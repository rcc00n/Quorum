import { ReasoningPreviewPage } from "@/components/reasoning-preview";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ event?: string; date?: string; version?: string }>;
}) {
  const q = await searchParams;
  return (
    <ReasoningPreviewPage
      key={`${q.date || "current"}:${q.version || "current"}`}
      eventId={q.event || ""}
      day={q.date || ""}
      version={q.version || ""}
    />
  );
}
