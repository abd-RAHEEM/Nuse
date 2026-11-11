"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiMode } from "@/lib/api/client";

type IconName = "grid" | "briefcase" | "bookmark" | "sliders" | "plus" | "arrow" | "external" | "clock" | "check";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    briefcase: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></>,
    bookmark: <path d="M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18l-6-4-6 4V4Z" />,
    sliders: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="8" cy="18" r="2" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const navItems = [
  { href: "/", label: "Dashboard", icon: "grid" as const },
  { href: "/jobs", label: "Jobs", icon: "briefcase" as const },
  { href: "/resources", label: "Resources", icon: "bookmark" as const },
  { href: "/settings", label: "Settings", icon: "sliders" as const },
];

export function NuseShell({ children, title, eyebrow }: { children: ReactNode; title: string; eyebrow?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [captureOpen, setCaptureOpen] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [profile, setProfile] = useState({ name: "Abdul", initials: "AR" });

  useEffect(() => {
    let active = true;
    if (apiMode === "mock") {
      window.requestAnimationFrame(() => {
        if (!active) return;
        if (window.localStorage.getItem("nuse-demo-session") === "active") {
          setAuthChecked(true);
        } else {
          router.replace("/login");
        }
      });
      return () => { active = false; };
    }
    void api.auth.me()
      .then((user) => {
        if (!active) return;
        const name = user.displayName?.trim() || user.username;
        const initials = name
          .split(/\s+/)
          .slice(0, 2)
          .map((part) => part[0] ?? "")
          .join("")
          .toUpperCase();
        setProfile({ name, initials });
        setAuthChecked(true);
      })
      .catch(() => { if (active) router.replace("/login"); });
    return () => { active = false; };
  }, [router]);

  if (!authChecked) {
    return <main className="auth-page" aria-busy="true"><div className="auth-loading">Opening your private desk…</div></main>;
  }

  return (
    <div className="app-shell">
      <aside className="side-rail">
        <Link href="/" className="wordmark" aria-label="Nuse home"><span className="wordmark-mark">n</span><span>Nuse</span></Link>
        <div className="rail-rule" />
        <nav className="primary-nav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return <Link key={item.href} href={item.href} aria-label={item.label} className={`nav-item ${active ? "is-active" : ""}`}><Icon name={item.icon} /><span>{item.label}</span></Link>;
          })}
        </nav>
        <div className="rail-bottom">
          <button className="capture-rail-button" onClick={() => setCaptureOpen(true)}><Icon name="plus" size={17} /><span>Capture</span><kbd>C</kbd></button>
          <div className="profile-chip"><span className="avatar">{profile.initials}</span><span><strong>{profile.name}</strong><small>Personal desk</small></span><span className="profile-dot" /></div>
        </div>
      </aside>
      <main className="main-column">
        <header className="topbar">
          <div><p className="eyebrow">{eyebrow ?? "Your career desk"}</p><h1>{title}</h1></div>
          <div className="top-actions"><button className="quiet-button search-button" aria-label="Search"><span className="search-key">/</span> Search</button><button className="primary-button" onClick={() => setCaptureOpen(true)}><Icon name="plus" size={16} /> Capture</button></div>
        </header>
        <div className="content-wrap">{children}</div>
      </main>
      <nav className="mobile-nav" aria-label="Mobile navigation">{navItems.map((item) => { const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href); return <Link key={item.href} href={item.href} aria-label={item.label} className={active ? "is-active" : ""}><Icon name={item.icon} size={19} /><span>{item.label}</span></Link>; })}<button className="mobile-capture" onClick={() => setCaptureOpen(true)} aria-label="Open capture"><Icon name="plus" size={21} /></button></nav>
      {captureOpen && <CaptureSheet onClose={() => setCaptureOpen(false)} />}
    </div>
  );
}

function CaptureSheet({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<"job" | "resource">("job");
  const [input, setInput] = useState("");
  const [working, setWorking] = useState(false);
  const [step, setStep] = useState(0);
  const steps = ["Read source", "Parse details", "Shape draft"];

  useEffect(() => {
    if (!working || step >= steps.length - 1) return;
    const timer = window.setTimeout(() => setStep((current) => current + 1), 800);
    return () => window.clearTimeout(timer);
  }, [working, step, steps.length]);

  const startCapture = () => {
    if (input.trim()) {
      setWorking(true);
      setStep(0);
    }
  };

  return <div className="sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="capture-sheet" role="dialog" aria-modal="true" aria-labelledby="capture-title">
      <div className="sheet-grip" /><div className="sheet-header"><div><p className="eyebrow">Smart capture</p><h2 id="capture-title">Put something useful in the desk.</h2></div><button className="icon-button" onClick={onClose} aria-label="Close capture">×</button></div>
      <div className="capture-tabs"><button className={mode === "job" ? "selected" : ""} onClick={() => setMode("job")}>Job <small>{mode === "job" ? "selected" : ""}</small></button><button className={mode === "resource" ? "selected" : ""} onClick={() => setMode("resource")}>Resource <small>{mode === "resource" ? "selected" : ""}</small></button></div>
      {working ? <div className="sheet-capture-progress" aria-live="polite"><p className="eyebrow">Capture path</p><h3>{step === steps.length - 1 ? "Draft ready to review" : "Turning this into a useful draft"}</h3><div className="sheet-flow">{steps.map((item, index) => <div className={`sheet-flow-step ${index < step ? "done" : ""} ${index === step ? "active" : ""}`} key={item}><span>{index < step ? "✓" : index + 1}</span><strong>{item}</strong>{index < steps.length - 1 && <i>→</i>}</div>)}</div>{step === steps.length - 1 && <button className="primary-button wide" onClick={onClose}>Review {mode} draft <Icon name="arrow" size={16} /></button>}</div> : <><div className="sheet-input ruled-input"><label htmlFor="sheet-url">Paste a URL or text</label><textarea id="sheet-url" value={input} onChange={(event) => setInput(event.target.value)} placeholder="https://... or paste the useful part here" autoFocus /></div><div className="capture-options">{mode === "job" ? <><span className="option-label">When this is a job</span><button className="option-pill selected">Save for later</button><button className="option-pill">I&apos;ve applied</button></> : <><span className="option-label">We&apos;ll suggest a category</span><span className="source-note">You review everything before it is saved.</span></>}</div><button className="primary-button wide" disabled={!input.trim()} onClick={startCapture}>Start capture <Icon name="arrow" size={16} /></button></>}
    </section>
  </div>;
}

export { Icon };
