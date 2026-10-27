import { Portal } from "@/components/portal";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "First setup" };
export default function Page() {
  return <Portal view="onboarding" />;
}
