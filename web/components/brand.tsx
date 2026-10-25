import Link from "next/link";
export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="Quorum home">
      <span className="brandmark" aria-hidden="true">
        q
      </span>
      quorum<span className="brand-dot">.</span>
    </Link>
  );
}
