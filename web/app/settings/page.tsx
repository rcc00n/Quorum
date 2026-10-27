import { Portal } from "@/components/portal";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "My topics" };
export default function Page() {
  return <Portal view="settings" />;
}
