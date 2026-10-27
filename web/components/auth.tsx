"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "@/lib/api";
import { ThemeToggle } from "./theme-toggle";
import "@/app/gate.css";

// DECISION(2026-10-26, Anastasia/Claude Code): sign-in and sign-up share one gate screen in the portal's identity,
// light by default like the landing and dark on the user's switch (the prototype's dark first screen): one
// grotesque, square corners, an ink button on paper or a paper button on ink; the field
// names, labels and button texts stay exactly as the smoke test and the backend expect (username, password,
// "Create account", "Sign in"). Why: WEB-UX-02 asked for a proper form; the API and its contract are Vadim's.
export function Auth({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      await api<{ user: User }>(register ? "register" : "login", {
        username: f.get("username"),
        password: f.get("password"),
      });
      router.replace(register ? "/onboarding" : "/dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="gate auth">
      <header className="gate-head">
        <Link href="/" className="gate-masthead" aria-label="Quorum home">
          Quorum
        </Link>
        <div className="gate-actions">
          <ThemeToggle />
          <Link href={register ? "/login" : "/register"} className="gate-link">
            {register ? "Sign in" : "Create account"}
          </Link>
        </div>
      </header>
      <div className="gate-body gate-grid">
        <div className="gate-story">
          <p className="gate-kicker">{register ? "Sign up" : "Sign in"}</p>
          <h1>{register ? "Choose your topics. Read the working." : "Welcome back."}</h1>
          <p className="gate-lead">
            {register
              ? "A login and a password, then the topics you follow. One edition per topic per day, prepared after the 05:30 New York cut; nothing is sold and nothing is shared."
              : "Your topics, the day's edition and the evidence under every line."}
          </p>
        </div>
        <div className="gate-form">
          <h2>{register ? "Create your account" : "Sign in to Quorum"}</h2>
          <p>{register ? "Free, no subscription. Pick a username; no email is required." : "Use the username you registered with."}</p>
          <form onSubmit={submit}>
            <label>
              Username
              <input name="username" autoComplete="username" required maxLength={150} />
            </label>
            <label>
              Password
              <input
                type="password"
                name="password"
                autoComplete={register ? "new-password" : "current-password"}
                required
                minLength={register ? 8 : 1}
              />
            </label>
            {register && <p className="help">At least 8 characters; common passwords are refused.</p>}
            {error && (
              <p className="message error" role="alert">
                {error}
              </p>
            )}
            <button disabled={busy} className="button">
              {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            </button>
          </form>
          <p className="gate-switch">
            {register ? "Already have an account?" : "New to Quorum?"}{" "}
            <Link href={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link>
          </p>
        </div>
      </div>
    </main>
  );
}
