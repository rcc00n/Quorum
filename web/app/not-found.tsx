import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="empty">
      <p className="eyebrow">404 / PAGE NOT FOUND</p>
      <h1>Let’s find your perspective.</h1>
      <Link className="button" href="/dashboard">
        Return to your brief
      </Link>
    </main>
  );
}
