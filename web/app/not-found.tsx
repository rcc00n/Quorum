import Link from "next/link";
import "./gate.css";
// DECISION(2026-10-27, Anastasia/Claude Code): the 404 page carries the masthead on the gate screens' surface
// (light, dark on the viewer's switch) instead of standing bare. Why: a reader who mistypes a link saw a page
// with no way back but a button whose text the shared empty-state rule had turned ink on ink.
export default function NotFound() {
  return (
    <div className="gate">
      <header className="gate-head">
        <Link href="/" className="gate-masthead" aria-label="Quorum home">
          Quorum
        </Link>
      </header>
      <main id="main" className="empty gate-body">
        <p className="eyebrow">404 / PAGE NOT FOUND</p>
        <h1>Let’s find your perspective.</h1>
        <Link className="button" href="/dashboard">
          Return to your brief
        </Link>
      </main>
    </div>
  );
}
