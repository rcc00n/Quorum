"use client";
import Link from "next/link";
import "./gate.css";
// The error page shares the 404 page's masthead and surface (see not-found.tsx).
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div className="gate">
      <header className="gate-head">
        <Link href="/" className="gate-masthead" aria-label="Quorum home">
          Quorum
        </Link>
      </header>
      <main id="main" className="empty gate-body">
        <h1>Something interrupted your reading.</h1>
        <p>Please try loading this page again.</p>
        <button className="button" onClick={reset}>
          Try again
        </button>
      </main>
    </div>
  );
}
