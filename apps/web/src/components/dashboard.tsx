"use client";

/* eslint-disable @next/next/no-html-link-for-pages */
import { useEffect, useState, type CSSProperties } from "react";
import { api, apiMode, ApiError } from "@/lib/api/client";
import type {
  DashboardResponse,
  Extraction,
  GmailSyncRun,
  ResourceCategory,
} from "@/types/api";
import { CalendarEventDialog } from "@/components/calendar-event-dialog";
import { Icon } from "./nuse-shell";

const captureSteps = ["Reading the source", "Parsing useful details", "Structuring your draft", "Ready to review"];

export function CaptureCard() {
  const [kind, setKind] = useState<"job" | "resource">("job");
  const [value, setValue] = useState("");
  const [pointer, setPointer] = useState({ x: "80%", y: "25%" });
  const [captureStep, setCaptureStep] = useState(-1);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [captureError, setCaptureError] = useState("");
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewCompany, setReviewCompany] = useState("");
  const [reviewDescription, setReviewDescription] = useState("");
  const [reviewCategory, setReviewCategory] = useState<ResourceCategory>("other");
  const [savingReview, setSavingReview] = useState(false);

  useEffect(() => {
    if (captureStep < 0 || captureStep >= captureSteps.length - 1) return;
    const timer = window.setTimeout(() => setCaptureStep((step) => step + 1), 850);
    return () => window.clearTimeout(timer);
  }, [captureStep]);

  const startCapture = async () => {
    if (!value.trim()) return;
    setCaptureError("");
    setCaptureStep(0);
    if (apiMode !== "live") return;
    try {
      const looksLikeUrl = /^https?:\/\//i.test(value.trim());
      const created = await api.extractions.create(
        looksLikeUrl ? { type: kind, url: value.trim() } : { type: kind, text: value.trim() },
      );
      setExtraction(created);
      const result = created.result ?? {};
      setReviewTitle(String(result.title?.value ?? ""));
      setReviewCompany(String(result.company?.value ?? ""));
      setReviewDescription(String(result.description?.value ?? ""));
      setReviewCategory((result.category?.value as ResourceCategory | undefined) ?? "other");
      setCaptureStep(captureSteps.length - 1);
    } catch (error) {
      setCaptureStep(-1);
      setCaptureError(error instanceof ApiError ? error.message : "The capture could not be started.");
    }
  };

  const saveReview = async () => {
    if (!extraction || !reviewTitle.trim() || (kind === "job" && !reviewCompany.trim())) return;
    setSavingReview(true);
    try {
      if (kind === "job") {
        await api.jobs.create({
          intent: "saved",
          company: reviewCompany.trim(),
          title: reviewTitle.trim(),
          sourceUrl: extraction.input.url ?? undefined,
          description: reviewDescription.trim() || undefined,
          extractionId: extraction.id,
        });
      } else {
        await api.resources.create({
          title: reviewTitle.trim(),
          category: reviewCategory,
          sourceUrl: extraction.input.url ?? undefined,
          description: reviewDescription.trim() || undefined,
          extractionId: extraction.id,
        });
      }
      setValue("");
      setExtraction(null);
      setCaptureStep(-1);
    } catch (error) {
      setCaptureError(error instanceof ApiError ? error.message : "The reviewed draft could not be saved.");
    } finally {
      setSavingReview(false);
    }
  };

  return <section className="capture-card" style={{ "--pointer-x": pointer.x, "--pointer-y": pointer.y } as CSSProperties} onPointerMove={(event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    setPointer({ x: `${((event.clientX - bounds.left) / bounds.width) * 100}%`, y: `${((event.clientY - bounds.top) / bounds.height) * 100}%` });
  }} aria-labelledby="capture-card-title">
    <div className="blueprint-crosshair crosshair-a" /><div className="blueprint-crosshair crosshair-b" />
    <div className="index-tab-row"><button className={kind === "job" ? "index-tab selected" : "index-tab"} onClick={() => setKind("job")}>Job <span>{kind === "job" ? "selected" : "1"}</span></button><button className={kind === "resource" ? "index-tab selected" : "index-tab"} onClick={() => setKind("resource")}>Resource <span>{kind === "resource" ? "selected" : "2"}</span></button></div>
    <div className="capture-card-top"><div><p className="eyebrow">Smart capture</p><h2 id="capture-card-title">Save the next useful thing.</h2></div><span className="capture-glyph"><span /></span></div>
    <div className="capture-field-wrap"><label htmlFor="capture-input">Paste a URL or text</label><textarea id="capture-input" value={value} onChange={(event) => setValue(event.target.value)} placeholder="A job link, article, course, tool, or a note from the web..." /><span className="field-line" /></div>
    {captureError && <p className="auth-error" role="alert">{captureError}</p>}
    {captureStep >= 0 ? <div className="capture-progress" aria-live="polite"><div className="capture-progress-head"><span className="eyebrow">Capture path</span><span>{captureStep === captureSteps.length - 1 ? "Review before saving" : apiMode === "live" ? "Reading the source" : "Working locally"}</span></div><div className="capture-flow">{captureSteps.map((step, index) => <span className={`capture-flow-step ${index < captureStep ? "done" : ""} ${index === captureStep ? "active" : ""}`} key={step}><i>{index < captureStep ? "✓" : index + 1}</i><b>{step}</b>{index < captureSteps.length - 1 && <em>→</em>}</span>)}</div>{extraction?.error && <p className="capture-fallback">{extraction.error.message}</p>}{extraction?.duplicateOf && <p className="capture-duplicate">Already saved as “{extraction.duplicateOf.title}”. Review carefully before saving again.</p>}{extraction?.result && <div className="capture-review"><label>Title<input value={reviewTitle} onChange={(event) => setReviewTitle(event.target.value)} required /></label>{kind === "job" && <label>Company<input value={reviewCompany} onChange={(event) => setReviewCompany(event.target.value)} required />{!reviewCompany.trim() && <small className="field-help">Add the company before saving this job.</small>}</label>}{kind === "resource" && <label>Category<select value={reviewCategory} onChange={(event) => setReviewCategory(event.target.value as ResourceCategory)}><option value="other">Other</option><option value="article">Article</option><option value="course">Course</option><option value="ai_tool">AI tool</option><option value="research">Research</option><option value="developer_resource">Developer resource</option></select></label>}<label>Description<textarea value={reviewDescription} onChange={(event) => setReviewDescription(event.target.value)} rows={4} /></label><button className="primary-button" onClick={saveReview} disabled={savingReview || !reviewTitle.trim() || (kind === "job" && !reviewCompany.trim())}>{savingReview ? "Saving reviewed draft…" : `Save ${kind}`} <Icon name="check" size={15} /></button></div>}<button className="quiet-button capture-reset" onClick={() => { setCaptureStep(-1); setExtraction(null); }}>Edit input</button></div> : <div className="capture-card-footer"><span className="capture-hint">{value ? "Source detected · ready to review" : "Nothing is saved until you review it"}</span><button className="primary-button" disabled={!value.trim()} onClick={startCapture}><span>{kind === "job" ? "Capture job" : "Capture resource"}</span><Icon name="arrow" size={15} /></button></div>}
  </section>;
}

const upcoming = [
  { company: "Kite Systems", role: "ML Platform Engineer", type: "Follow-up", date: "Tomorrow", tone: "mint", initials: "KS" },
  { company: "Mango Labs", role: "Applied AI Intern", type: "Technical interview", date: "Thu, Nov 5", tone: "lavender", initials: "ML" },
  { company: "Northstar Health", role: "Data Science Fellow", type: "Assessment", date: "Nov 9", tone: "amber", initials: "NH" },
];
const resources = [
  { title: "Building reliable RAG evaluations", source: "Pinecone · Article", age: "Added today", glyph: "↗" },
  { title: "Practical Deep Learning for Coders", source: "fast.ai · Course", age: "Yesterday", glyph: "◫" },
  { title: "The ML engineer’s field guide", source: "GitHub · Developer resource", age: "3 days ago", glyph: "⌘" },
];

function GmailSyncAction() {
  const [connected, setConnected] = useState(false);
  const [connectionLoaded, setConnectionLoaded] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [syncRun, setSyncRun] = useState<GmailSyncRun | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api.integrations.list()
      .then(({ items }) => {
        if (!active) return;
        const gmail = items.find((item) => item.provider === "gmail");
        setConnected(gmail?.status === "connected");
        const value = gmail?.config.lastSyncAt;
        setLastSyncAt(typeof value === "string" ? value : null);
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(
            loadError instanceof ApiError
              ? loadError.message
              : "Gmail connection status could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (active) setConnectionLoaded(true);
      });
    return () => { active = false; };
  }, []);

  const sync = async () => {
    setSyncing(true);
    setError("");
    setNotice("");
    try {
      let run = await api.integrations.startGmailSync();
      setSyncRun(run);
      let steps = 0;
      while (run.status === "running" && steps < 300) {
        if (steps > 0) {
          await new Promise<void>((resolve) => window.setTimeout(resolve, 250));
        }
        run = await api.integrations.advanceGmailSync(run.id);
        setSyncRun(run);
        steps += 1;
      }
      if (run.status === "completed") {
        setNotice(
          `Checked ${run.messagesScanned} messages. Updated ${run.jobsUpdated} jobs, queued ${run.reviewQueued} for review, and discarded ${run.unmatchedDiscarded} unmatched.`,
        );
        setLastSyncAt(run.finishedAt);
      } else if (run.status === "running") {
        setNotice(
          `Sync paused after ${run.messagesScanned} messages. Sync again to resume.`,
        );
      } else {
        setError(run.lastError ?? "Gmail sync could not be completed.");
      }
    } catch (syncError) {
      setError(
        syncError instanceof ApiError
          ? syncError.message
          : "Gmail could not be synced. The saved progress can be resumed.",
      );
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="gmail-quick-action">
      {connected ? (
        <button
          className="quiet-button gmail-sync-button"
          type="button"
          onClick={() => void sync()}
          disabled={syncing || !connectionLoaded}
        >
          {syncing
            ? `Checking ${syncRun?.messagesScanned ?? 0} messages…`
            : "Sync Gmail"}
        </button>
      ) : (
        <a className="quiet-button gmail-sync-button" href="/settings">
          Connect Gmail
        </a>
      )}
      {lastSyncAt && !syncing && (
        <small>
          Last synced {new Date(lastSyncAt).toLocaleString("en-IN")}
        </small>
      )}
      {notice && <p className="gmail-sync-notice" role="status">{notice}</p>}
      {error && <p className="gmail-sync-notice error" role="alert">{error}</p>}
      {syncRun?.status === "completed" && syncRun.reviewQueued > 0 && (
        <a className="text-button" href="/jobs">
          Review matched emails
        </a>
      )}
    </div>
  );
}

export function DashboardContent() {
  const [liveDashboard, setLiveDashboard] = useState<DashboardResponse | null>(null);
  const [liveError, setLiveError] = useState("");
  const [calendarOpen, setCalendarOpen] = useState(false);

  useEffect(() => {
    if (apiMode !== "live") return;
    api.dashboard.get().then(setLiveDashboard).catch(() => {
      setLiveError("The live dashboard could not be loaded. Check that the API is running.");
    });
  }, []);

  const liveUpcoming = liveDashboard?.upcoming ?? [];
  const liveResources = liveDashboard?.recentResources ?? [];
  const displayUpcoming = apiMode === "live"
    ? liveUpcoming.map((item) => ({
      company: item.job.company,
      role: item.job.title,
      type: item.kind.replace("_", " "),
      date: new Date(item.at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
      tone: item.overdue ? "amber" : "mint",
      initials: item.job.company.slice(0, 2).toUpperCase(),
    }))
    : upcoming;
  const displayResources = apiMode === "live"
    ? liveResources.map((item) => ({
      title: item.title,
      source: item.sourcePlatform ?? "Saved resource",
      age: new Date(item.createdAt).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
      glyph: "◫",
    }))
    : resources;

  return <div className="dashboard-stack">
    <div className="hero-intro"><div><p className="eyebrow">{apiMode === "live" ? "Your private desk" : "Saturday, November 1"}</p><h2>Good {apiMode === "live" ? "day" : "evening"}, {liveDashboard?.user.displayName ?? liveDashboard?.user.username ?? "Abdul"}.</h2><p className="hero-copy">{liveError || (liveDashboard ? `${liveDashboard.counts.applicationsTracked} applications are in motion.` : "One small action now makes next week easier.")}</p></div><span className="coordinate">X: 142&nbsp;&nbsp;Y: 08</span></div>
    <CaptureCard />
    {apiMode === "live" && (
      <div className="dashboard-quick-actions">
        <div className="calendar-quick-action">
          <span>Have an interview, assessment, or reminder to schedule?</span>
          <button className="text-button" onClick={() => setCalendarOpen(true)}>Add a calendar event</button>
        </div>
        <GmailSyncAction />
      </div>
    )}
    <div className="metric-row"><a href="/jobs?status%5B%5D=applied" className="metric-card metric-amber"><span className="metric-label">Applications tracked</span><strong>{liveDashboard?.counts.applicationsTracked ?? (apiMode === "live" ? "—" : 18)}</strong><span>Keep the next action visible <Icon name="arrow" size={14} /></span></a><a href="/jobs?status%5B%5D=interview" className="metric-card metric-mint"><span className="metric-label">Interviews active</span><strong>{liveDashboard?.counts.interviewsActive ?? (apiMode === "live" ? "—" : 3)}</strong><span>Review the week ahead <Icon name="arrow" size={14} /></span></a><div className="metric-note"><span className="note-mark">+</span><span>Keep the desk current<br /><b>Review, then move one forward.</b></span></div></div>
    <div className="dashboard-grid"><section className="ledger-section"><div className="section-heading"><div><p className="eyebrow">Next on the desk</p><h3>Coming up</h3></div><a href="/jobs">View all <Icon name="arrow" size={14} /></a></div>{displayUpcoming.map((item) => <a className="upcoming-row" href="/jobs" key={`${item.company}-${item.role}`}><span className={`company-mark ${item.tone}`}>{item.initials}</span><span className="row-main"><strong>{item.role}</strong><small>{item.company} · {item.type}</small></span><span className="row-date">{item.date}<Icon name="arrow" size={14} /></span></a>)}</section><section className="ledger-section"><div className="section-heading"><div><p className="eyebrow">Filed recently</p><h3>Resources</h3></div><a href="/resources">Open library <Icon name="arrow" size={14} /></a></div>{displayResources.map((item) => <a className="resource-row" href="/resources" key={item.title}><span className="resource-glyph">{item.glyph}</span><span className="row-main"><strong>{item.title}</strong><small>{item.source}</small></span><span className="row-date">{item.age}</span></a>)}</section></div>
    <section className="activity-section"><div className="section-heading"><div><p className="eyebrow">A quiet record</p><h3>Recent activity</h3></div><a href="/jobs">Timeline <Icon name="arrow" size={14} /></a></div><div className="activity-line">{apiMode === "live" ? (liveDashboard?.recentActivity ?? []).map((item) => <div className="activity-item" key={item.id}><span className="timeline-dot filled" /><span><strong>{item.title}</strong><small>{item.job.company} · {new Date(item.occurredAt).toLocaleString("en-IN")}</small></span></div>) : <><div className="activity-item"><span className="timeline-dot filled" /><span><strong>Applied to ML Platform Engineer</strong><small>Kite Systems · Today, 10:42</small></span></div><div className="activity-item"><span className="timeline-dot" /><span><strong>Saved a developer resource</strong><small>GitHub · Yesterday, 18:20</small></span></div><div className="activity-item"><span className="timeline-dot" /><span><strong>Moved Applied AI Intern to interview</strong><small>Mango Labs · Oct 29, 14:06</small></span></div></>}</div></section>
    {calendarOpen && <CalendarEventDialog onClose={() => setCalendarOpen(false)} />}
  </div>;
}
