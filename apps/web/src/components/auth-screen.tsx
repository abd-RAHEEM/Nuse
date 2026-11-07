"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, apiMode, ApiError } from "@/lib/api/client";

type AuthMode = "login" | "signup";

const USER_KEY = "nuse-demo-user";

export function AuthScreen({ mode }: { mode: AuthMode }) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [pin, setPin] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [remember, setRemember] = useState(true);
  const router = useRouter();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!/^[a-z0-9_.-]{3,32}$/.test(username.toLowerCase())) {
      setError("Use 3–32 lowercase letters, numbers, dots, underscores, or hyphens.");
      return;
    }
    if (!/^\d{6}$/.test(pin)) {
      setError("Your PIN must contain exactly six digits.");
      return;
    }

    if (apiMode === "live") {
      try {
        if (mode === "signup") {
          await api.auth.signup(username.toLowerCase(), pin);
        } else {
          await api.auth.login(username.toLowerCase(), pin);
        }
        router.push("/");
      } catch (caughtError) {
        setError(caughtError instanceof ApiError ? caughtError.message : "The desk could not be opened.");
      }
      return;
    }

    if (mode === "signup") {
      if (localStorage.getItem(USER_KEY)) {
        setError("This browser already has a Nuse desk. Sign in to continue.");
        return;
      }
      localStorage.setItem(USER_KEY, JSON.stringify({ username: username.toLowerCase(), displayName: displayName.trim() || username }));
      setNotice("Your Nuse desk is ready. You can sign in now.");
      return;
    }

    localStorage.setItem("nuse-demo-session", remember ? "active" : "session");
    router.push("/");
  };

  return <main className="auth-page">
    <div className="auth-blueprint auth-blueprint-a" /><div className="auth-blueprint auth-blueprint-b" />
    <section className="auth-panel">
      <Link href="/" className="auth-wordmark"><span className="wordmark-mark">n</span><span>Nuse</span></Link>
      <div className="auth-copy"><p className="eyebrow">{mode === "login" ? "Your private career desk" : "Set up your private desk"}</p><h1>{mode === "login" ? "Pick up where you left off." : "Make a place for what comes next."}</h1><p>{mode === "login" ? "Your applications, resources, and next actions are waiting." : "Nuse keeps the useful things you find close, clear, and ready to act on."}</p></div>
      <form className="auth-form" onSubmit={handleSubmit}>
        {mode === "signup" && <label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="How should Nuse greet you?" autoComplete="name" /></label>}
        <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="e.g. abdul.raheem" autoComplete="username" /></label>
        <p className="field-hint">3–32 characters: lowercase letters, numbers, dots, underscores, or hyphens.</p>
        <label>Six-digit PIN<input className="pin-input" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="••••••" inputMode="numeric" autoComplete={mode === "login" ? "current-password" : "new-password"} maxLength={6} /></label>
        {mode === "signup" ? <div className="auth-note"><span>i</span><p>This PIN cannot be recovered in v1. Choose one you can remember and do not reuse a banking PIN.</p></div> : <label className="remember-row"><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} /> Keep me signed in on this browser</label>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {notice && <p className="auth-success" role="status">{notice}</p>}
        <button className="primary-button wide" type="submit">{mode === "login" ? "Open Nuse" : "Create my desk"}<span aria-hidden="true">→</span></button>
      </form>
      <div className="auth-footer">{mode === "login" ? <><span>First time here?</span><Link href="/signup">Create an account</Link></> : <><span>Already have a desk?</span><Link href="/login">Sign in</Link></>}</div>
    </section>
    <aside className="auth-side-note"><span className="auth-note-line" /><p>Capture first.<br />Organize intelligently.</p><small>Private by design · Nuse</small></aside>
  </main>;
}
