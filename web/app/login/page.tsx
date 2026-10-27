import { Auth } from "@/components/auth";
import type { Metadata } from "next";
export const metadata: Metadata = { title: "Sign in" };
export default function Page() {
  return <Auth />;
}
