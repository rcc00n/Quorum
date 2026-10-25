import Link from "next/link";
import {
  ArrowUpRight,
  ArrowRight,
  ScanText,
  Network,
  BookOpen,
} from "lucide-react";
import { Brand } from "@/components/brand";
export default function Home() {
  return (
    <>
      <header className="public-header">
        <Brand />
        <nav>
          <a href="#approach">Our approach</a>
          <Link href="/login">Sign in</Link>
          <Link className="button small" href="/register">
            Create account <ArrowUpRight size={15} />
          </Link>
        </nav>
      </header>
      <main id="main">
        <section className="hero">
          <div className="hero-inner">
            <p className="eyebrow">INDEPENDENT PERSPECTIVE. SHARED EVIDENCE.</p>
            <h1>
              See the
              <br />
              <em>whole story.</em>
            </h1>
            <p className="hero-copy">
              The news is complicated. Your understanding doesn’t have to be.
              Follow the evidence, compare perspectives, and know what remains
              uncertain.
            </p>
            <Link href="/register" className="button">
              Build your daily brief <ArrowRight size={18} />
            </Link>
            <p className="hero-note">Your topics. A clearer starting point.</p>
          </div>
          <div className="editorial-art" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="art-center">
              q<span>.</span>
            </div>
            <span className="art-label label-one">EVIDENCE</span>
            <span className="art-label label-two">PERSPECTIVE</span>
            <span className="art-label label-three">CONTEXT</span>
            <div className="art-caption">MANY SOURCES. A CLEARER PICTURE.</div>
          </div>
          <div className="hero-bottom">
            <span>READ WITH PERSPECTIVE</span>
            <span>↓ EXPLORE THE APPROACH</span>
          </div>
        </section>
        <section id="approach" className="approach">
          <div>
            <p className="eyebrow">A MORE CONSIDERED BRIEF</p>
            <h2>
              Clarity begins
              <br />
              with better questions.
            </h2>
          </div>
          <div className="principles">
            {[
              [
                ScanText,
                "What is established?",
                "Evidence and source links sit beside every conclusion, with statements kept separate from verified facts.",
              ],
              [
                Network,
                "How does coverage differ?",
                "Compare how outlets frame an event. External ratings describe source positions, with missing data made visible.",
              ],
              [
                BookOpen,
                "What is still unknown?",
                "Disputed claims and unanswered questions stay in view. Uncertainty is part of understanding.",
              ],
            ].map(([Icon, title, body], i) => {
              const I = Icon as typeof ScanText;
              return (
                <article key={i}>
                  <I size={22} />
                  <div>
                    <h3>{title as string}</h3>
                    <p>{body as string}</p>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
        <section className="final-cta">
          <p className="eyebrow">MAKE ROOM FOR UNDERSTANDING</p>
          <h2>A daily brief, shaped around you.</h2>
          <Link className="button" href="/register">
            Choose your topics <ArrowUpRight size={18} />
          </Link>
        </section>
      </main>
      <footer>
        <Brand />
        <p>Evidence first. Perspective always.</p>
        <Link href="/login">Sign in →</Link>
      </footer>
    </>
  );
}
