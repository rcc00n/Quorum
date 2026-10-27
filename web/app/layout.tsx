import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/schibsted-grotesk";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "Quorum — The news, with its working shown", template: "%s · Quorum" },
  description:
    "One event, read across the political spectrum and official documents: what is known, what is claimed, and the evidence under every line.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
