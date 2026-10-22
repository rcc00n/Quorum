"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Brand } from "./brand";
import { api, User } from "@/lib/api";
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
    <main id="main" className="auth-page">
      <div className="auth-story">
        <Brand />
        <div>
          <p className="eyebrow">A CLEARER DAILY PERSPECTIVE</p>
          <h1>
            Stay curious.
            <br />
            <em>Stay informed.</em>
          </h1>
          <p>Understand the evidence behind the headlines.</p>
        </div>
        <span>QUORUM / EDITORIAL INTELLIGENCE</span>
      </div>
      <div className="auth-form">
        <Link className="back" href="/">
          ← Back to Quorum
        </Link>
        <p className="eyebrow">
          {register ? "YOUR PERSPECTIVE STARTS HERE" : "WELCOME BACK"}
        </p>
        <h2>{register ? "Create your account" : "Sign in to Quorum"}</h2>
        <p>
          {register
            ? "A thoughtful brief starts with your interests."
            : "Your topics, evidence and daily perspective."}
        </p>
        <form onSubmit={submit}>
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={150}
            />
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
          {register && (
            <p className="help">
              Use at least 8 characters and avoid common passwords.
            </p>
          )}
          {error && (
            <p className="message error" role="alert">
              {error}
            </p>
          )}
          <button disabled={busy} className="button">
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            <ArrowRight size={16} />
          </button>
        </form>
        <p className="auth-switch">
          {register ? "Already have an account?" : "New to Quorum?"}{" "}
          <Link href={register ? "/login" : "/register"}>
            {register ? "Sign in" : "Create account"}
          </Link>
        </p>
      </div>
    </main>
  );
}
