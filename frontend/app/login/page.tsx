"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApiError, GOOGLE_LOGIN_URL, setToken } from "@/lib/api";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-shell" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { user, loading, login, register, refresh } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // The password form is the fallback, not the front door: it's only reachable
  // at /login?password=1, so a broken OAuth client can't lock anyone out.
  const passwordMode = searchParams.get("password") === "1";
  const [mode, setMode] = useState<"login" | "register">(
    searchParams.get("mode") === "register" ? "register" : "login"
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [returning, setReturning] = useState(false);

  // Coming back from /auth/google/callback. The token is in the URL *fragment*,
  // which browsers never send to a server, so it stays out of access logs and
  // the Referer header. Read it, store it, and scrub it from the address bar.
  useEffect(() => {
    if (typeof window === "undefined" || !window.location.hash) return;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get("token");
    const failure = params.get("error");
    window.history.replaceState(null, "", window.location.pathname);
    if (failure) {
      setError(failure);
      return;
    }
    if (token) {
      setReturning(true);
      setToken(token);
      refresh().then(() => router.replace("/dashboard"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (returning) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="auth-title">Signing you in…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <Link href="/" className="brand" style={{ padding: "0 0 20px 0", textDecoration: "none" }}>
          <div className="brand-mark" />
          <div className="brand-name">Signal</div>
        </Link>
        <div className="auth-title">{mode === "login" ? "Welcome back" : "Create your account"}</div>
        <div className="auth-sub">
          {mode === "login"
            ? "Sign in to run audits on your sites."
            : "Free to start — no card, and credits included to try the paid parts."}
        </div>

        {error && <div className="form-error">{error}</div>}

        {!passwordMode ? (
          <>
            <a className="btn-google" href={GOOGLE_LOGIN_URL}>
              <GoogleMark />
              Continue with Google
            </a>
            <p className="auth-fineprint">
              We ask Google for your name and email address, nothing else. Connecting Search Console or Analytics is a
              separate step you take later, from Settings.
            </p>
            <div className="auth-switch">
              <Link href="/login?password=1">Use an email and password instead</Link>
            </div>
          </>
        ) : (
          <>
            <form onSubmit={handleSubmit}>
              <div className="field">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                />
              </div>
              <div className="field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                />
              </div>
              <button className="btn full-width" type="submit" disabled={submitting}>
                {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>

            <div className="auth-switch">
              {mode === "login" ? (
                <>
                  New to Signal?{" "}
                  <button type="button" onClick={() => setMode("register")}>
                    Create an account
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button type="button" onClick={() => setMode("login")}>
                    Sign in
                  </button>
                </>
              )}
            </div>
            <div className="auth-switch">
              <Link href="/login">← Back to Google sign-in</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M45.1 24.5c0-1.6-.1-2.8-.4-4H24v7.3h12.1c-.2 2-1.6 5-4.5 7l-.1.3 6.5 5 .5.1c4.1-3.8 6.6-9.4 6.6-15.7"
      />
      <path
        fill="#34A853"
        d="M24 46c5.9 0 10.9-2 14.5-5.3l-6.9-5.4c-1.8 1.3-4.3 2.2-7.6 2.2-5.8 0-10.7-3.8-12.5-9.1l-.3.1-6.8 5.2-.1.3C7.9 41 15.4 46 24 46"
      />
      <path
        fill="#FBBC05"
        d="M11.5 28.4c-.5-1.4-.7-2.9-.7-4.4s.3-3.1.7-4.4v-.4l-6.9-5.3-.2.1C2.9 17 2 20.4 2 24s.9 7 2.4 10l7.1-5.6"
      />
      <path
        fill="#EB4335"
        d="M24 10.5c4.1 0 6.9 1.8 8.5 3.3l6.2-6C34.9 4.3 29.9 2 24 2 15.4 2 7.9 7 4.4 14l7.1 5.6c1.8-5.3 6.7-9.1 12.5-9.1"
      />
    </svg>
  );
}
