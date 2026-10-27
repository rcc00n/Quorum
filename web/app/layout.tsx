import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/schibsted-grotesk";
import "./globals.css";
import "./identity.css";
import "./workspace.css";
import "./header.css";
import "./spectrum.css";
import "./reader.css";
import "./navigator.css";
import "./instrument-polish.css";
import "./impact.css";
import { ScrollState } from "@/components/scroll-state";
export const metadata: Metadata = {
  title: { default: "Quorum — The news, with its working shown", template: "%s · Quorum" },
  description:
    "One event, read across the political spectrum and official documents: what is known, what is claimed, and the evidence under every line.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body>
        {/* The viewer's theme choice (web/components/theme-toggle.tsx) applied before first paint; light when unset. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('quorum-theme');if(t==='dark'||t==='light'){document.documentElement.dataset.theme=t}}catch(e){}",
          }}
        />
        <ScrollState />
        <a className="skip" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
