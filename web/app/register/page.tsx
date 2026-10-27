import { Auth } from "@/components/auth";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "Create account" };
export default function Page() {
  return <Auth register />;
}
