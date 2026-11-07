"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { api, apiMode } from "@/lib/api/client";
import type { JobSummary } from "@/types/api";
import { Icon } from "./nuse-shell";

type Job = { id?: string; company: string; initials: string; title: string; location: string; status: string; applied: string; followUp: string; tone: string; description: string };
const jobs: Job[] = [
  { company: "Kite Systems", initials: "KS", title: "ML Platform Engineer", location: "Bengaluru · Hybrid", status: "Applied", applied: "Nov 1, 2026", followUp: "Tomorrow", tone: "mint", description: "Build the internal platform that helps product teams ship reliable machine learning systems. The role sits between infrastructure and applied research." },
  { company: "Mango Labs", initials: "ML", title: "Applied AI Intern", location: "Hyderabad · On-site", status: "Interview", applied: "Oct 18, 2026", followUp: "Nov 5", tone: "lavender", description: "Work with a small applied research team to turn language model experiments into focused tools for customer support and operations." },
  { company: "Northstar Health", initials: "NH", title: "Data Science Fellow", location: "Remote · India", status: "Assessment", applied: "Oct 12, 2026", followUp: "Nov 9", tone: "amber", description: "Explore clinical operations data and help shape experiments that improve access, triage, and patient outcomes." },
  { company: "Saffron Cloud", initials: "SC", title: "Product Data Analyst", location: "Pune · Hybrid", status: "Saved", applied: "Oct 8, 2026", followUp: "No date yet", tone: "forest", description: "A cross-functional analytics role partnering closely with product and design on a fast-growing developer platform." },
];

function StageRail({ status }: { status: string }) {
  const stages = ["Saved", "Applied", "Assessment", "Interview", "Offer"];
  const current = stages.indexOf(status);
  return <div className="stage-rail" aria-label={`Current stage: ${status}`}>{stages.map((stage, index) => <span key={stage} className={index <= current ? "filled" : ""} title={stage} />)}</div>;
}

function JobCard({ job, expanded, onToggle, onAdvance, onArchive, onDelete }: { job: Job; expanded: boolean; onToggle: () => void; onAdvance: () => void; onArchive: () => void; onDelete: () => void }) {
  return <article className={`job-card ${expanded ? "expanded" : ""}`}><button className="job-summary" onClick={onToggle} aria-expanded={expanded}><span className={`company-mark ${job.tone}`}>{job.initials}</span><span className="job-title-block"><strong>{job.title}</strong><small>{job.company} · {job.location}</small></span><span className="job-status"><StageRail status={job.status} /><b>{job.status}</b></span><span className="job-follow"><small>Next action</small><strong>{job.followUp}</strong></span><span className="expand-control">{expanded ? "Collapse" : "Details"} <span className={expanded ? "rotated" : ""}>⌄</span></span></button>
    {expanded && <div className="job-expansion"><div className="job-analysis"><div className="analysis-main"><div className="analysis-heading"><span className="eyebrow">Full analysis</span><span className="source-chip">kite.systems <Icon name="external" size={12} /></span></div><p>{job.description}</p><div className="analysis-section"><span className="eyebrow">Why it fits</span><p className="analysis-copy">Strong overlap with your ML platform work, Python systems experience, and interest in reliable production tooling.</p></div><div className="analysis-facts"><span><small>Application date</small><strong>{job.applied}</strong></span><span><small>Work mode</small><strong>{job.location.split("·")[1]?.trim()}</strong></span><span><small>Source</small><strong>Company careers</strong></span><span><small>Signal</small><strong className="signal">High alignment</strong></span></div><div className="analysis-tags"><span>Python</span><span>Machine learning</span><span>Platform</span></div><div className="analysis-actions"><button className="primary-button small" onClick={onAdvance}>Mark as next stage <Icon name="arrow" size={14} /></button>    <Link className="quiet-button small" href={job.id ? `/jobs/${job.id}` : "/jobs"}>Open full record</Link><button className="quiet-button small" onClick={onArchive}>Archive</button><button className="quiet-button small" onClick={onDelete}>Delete</button></div></div><div className="analysis-side"><span className="eyebrow">Personal note</span><p>Prepare two examples that show calm ownership when the requirements are still moving.</p><button className="text-button">Edit note <Icon name="arrow" size={13} /></button><div className="analysis-side-block"><span className="eyebrow">Requirements</span><ul><li>Production Python experience</li><li>Comfort with ambiguous systems</li><li>Clear written communication</li></ul></div></div></div><div className="job-timeline"><div className="timeline-header"><span className="eyebrow">Application timeline</span><button className="text-button">Add event <Icon name="plus" size={13} /></button></div><div className="timeline-track"><div className="timeline-progress" /><TimelineEvent date="Nov 01" title="Job saved" detail="Found through company careers" /><TimelineEvent date={job.applied.replace(", 2026", "")} title="Applied" detail="Resume and portfolio submitted" filled /><TimelineEvent date={job.status === "Interview" ? "Nov 05" : "Next"} title={job.status === "Interview" ? "Technical interview" : "Next follow-up"} detail={job.status === "Interview" ? "Scheduled · 45 minutes" : "Keep the application moving"} scheduled={job.status !== "Interview"} /></div></div></div>}
  </article>;
}

function TimelineEvent({ date, title, detail, filled = false, scheduled = false }: { date: string; title: string; detail: string; filled?: boolean; scheduled?: boolean }) {
  return <div className={`timeline-event ${scheduled ? "scheduled" : ""}`}><span className={`event-marker ${filled ? "filled" : ""}`} /><span className="timeline-event-copy"><time>{date}</time><strong>{title}</strong><small>{detail}</small></span></div>;
}

function JobsAnalytics() {
  const stages = [
    { label: "Saved", count: 6, tone: "saved" },
    { label: "Applied", count: 7, tone: "applied" },
    { label: "Assessment", count: 2, tone: "assessment" },
    { label: "Interview", count: 3, tone: "interview" },
    { label: "Offer", count: 0, tone: "offer" },
  ];

  return <section className="jobs-analytics" aria-labelledby="analytics-title">
    <div className="analytics-heading"><div><p className="eyebrow">A clear view of the pipeline</p><h2 id="analytics-title">Your applications, at a glance.</h2></div><span className="analytics-updated">Updated just now</span></div>
    <div className="analytics-grid">
      <div className="pipeline-panel"><div className="analytics-label-row"><span className="eyebrow">Pipeline shape</span><span className="analytics-total">18 active</span></div><div className="pipeline-bars">{stages.map((stage) => <button className="pipeline-stage" key={stage.label}><span className={`pipeline-bar ${stage.tone}`} style={{ "--bar-size": `${Math.max(stage.count * 12, 4)}%` } as CSSProperties} /><span><b>{stage.count}</b><small>{stage.label}</small></span></button>)}</div></div>
      <div className="analytics-stat stat-mint"><span className="eyebrow">Interviews active</span><strong>3</strong><small>2 this week · 1 scheduled</small></div>
      <div className="analytics-stat stat-amber"><span className="eyebrow">Needs attention</span><strong>4</strong><small>Follow-ups due within 7 days</small></div>
      <div className="analytics-stat stat-lavender"><span className="eyebrow">Response signal</span><strong>42%</strong><small>Applications reaching a reply</small></div>
    </div>
  </section>;
}

export function JobsView() {
  const [liveJobs, setLiveJobs] = useState<Job[] | null>(null);
  const [liveError, setLiveError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [newCompany, setNewCompany] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [location, setLocation] = useState("All locations");
  const statuses = ["All", "Saved", "Applied", "Assessment", "Interview"];
  useEffect(() => {
    if (apiMode !== "live") return;
    api.jobs.list().then((result) => setLiveJobs(result.items.map(toDisplayJob))).catch(() => {
      setLiveError("The live jobs ledger could not be loaded. Check that the API is running.");
    });
  }, []);
  const sourceJobs = liveJobs ?? jobs;
  const visible = sourceJobs.filter((job) => `${job.title} ${job.company}`.toLowerCase().includes(query.toLowerCase()) && (status === "All" || job.status === status) && (location === "All locations" || job.location.includes(location)));
  const mutateJob = async (job: Job, action: "advance" | "archive" | "delete") => {
    if (apiMode !== "live" || !job.id) return;
    try {
      if (action === "delete") {
        await api.jobs.remove(job.id);
        setLiveJobs((current) => (current ?? []).filter((item) => item.id !== job.id));
        return;
      }
      if (action === "archive") {
        await api.jobs.update(job.id, { archived: true });
        setLiveJobs((current) => (current ?? []).filter((item) => item.id !== job.id));
        return;
      }
      const stages = ["Saved", "Applied", "Assessment", "Interview", "Offer"];
      const next = stages[Math.min(stages.indexOf(job.status) + 1, stages.length - 1)];
      if (next && next !== job.status) {
        const updated = await api.jobs.update(job.id, { status: next.toLowerCase() });
        setLiveJobs((current) => (current ?? []).map((item) => item.id === job.id ? toDisplayJob(updated) : item));
      }
    } catch {
      setLiveError(`The job could not be ${action === "delete" ? "deleted" : action === "archive" ? "archived" : "updated"}.`);
    }
  };
  const saveJob = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (apiMode !== "live" || !newCompany.trim() || !newTitle.trim()) return;
    setSaving(true);
    try {
      const created = await api.jobs.create({
        intent: "saved",
        company: newCompany.trim(),
        title: newTitle.trim(),
        location: newLocation.trim() || undefined,
        sourceUrl: newUrl.trim() || undefined,
      });
      setLiveJobs((current) => [toDisplayJob(created), ...(current ?? [])]);
      setAddOpen(false);
      setNewCompany("");
      setNewTitle("");
      setNewLocation("");
      setNewUrl("");
    } catch {
      setLiveError("The job could not be saved. Check the fields and try again.");
    } finally {
      setSaving(false);
    }
  };
  return <div className="jobs-stack"><JobsAnalytics /><div className="page-intro-row"><div><p className="eyebrow">The application ledger</p><p className="page-support">{liveError || (apiMode === "live" ? `${liveJobs?.length ?? "—"} active records` : "18 active records · 4 need your attention")}</p></div><div className="view-actions"><button className="quiet-button"><Icon name="sliders" size={15} /> More filters</button><button className="primary-button" onClick={() => setAddOpen(true)}><Icon name="plus" size={15} /> Add job</button></div></div><div className="job-filter-panel"><div className="filter-heading"><span className="eyebrow">Filter and find</span><span className="filter-count">{visible.length} visible</span></div><div className="filter-controls"><label className="search-field"><span>/</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search role or company" /></label><div className="filter-pills">{statuses.map((item) => <button key={item} className={status === item ? "active" : ""} onClick={() => setStatus(item)}>{item}</button>)}</div><select className="location-select" value={location} onChange={(event) => setLocation(event.target.value)} aria-label="Filter by location"><option>All locations</option><option>Remote</option><option>Hybrid</option><option>On-site</option></select></div></div><div className="jobs-toolbar"><div className="toolbar-tabs"><button className="active">Cards</button><button>Board</button></div><button className="sort-button">Newest first <span>⌄</span></button></div><div className="jobs-list">{visible.map((job) => { const key = job.id ?? job.title; const isExpanded = expanded.has(key); return <JobCard key={key} job={job} expanded={isExpanded} onAdvance={() => mutateJob(job, "advance")} onArchive={() => mutateJob(job, "archive")} onDelete={() => mutateJob(job, "delete")} onToggle={() => setExpanded((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; })} />; })}</div>{addOpen && <div className="sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddOpen(false); }}><section className="capture-sheet" role="dialog" aria-modal="true" aria-labelledby="add-job-title"><div className="sheet-grip" /><div className="sheet-header"><div><p className="eyebrow">Add a record</p><h2 id="add-job-title">Save a job to the desk.</h2></div><button className="icon-button" onClick={() => setAddOpen(false)} aria-label="Close add job">×</button></div><form className="auth-form" onSubmit={saveJob}><label>Company<input value={newCompany} onChange={(event) => setNewCompany(event.target.value)} required /></label><label>Role title<input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} required /></label><label>Location<input value={newLocation} onChange={(event) => setNewLocation(event.target.value)} placeholder="Remote, Bengaluru, or leave blank" /></label><label>Source URL<input type="url" value={newUrl} onChange={(event) => setNewUrl(event.target.value)} placeholder="https://..." /></label><button className="primary-button wide" type="submit" disabled={saving}>{saving ? "Saving job…" : "Save job"} <Icon name="arrow" size={15} /></button></form></section></div>}</div>;
}

function toDisplayJob(job: JobSummary): Job {
  const status = job.status.replace("_", " ");
  return {
    id: job.id,
    company: job.company,
    initials: job.company.slice(0, 2).toUpperCase(),
    title: job.title,
    location: [job.location, job.workMode?.replace("_", " ")].filter(Boolean).join(" · ") || "Location not listed",
    status: status.charAt(0).toUpperCase() + status.slice(1),
    applied: job.appliedOn ?? "Not applied",
    followUp: job.nextFollowUpOn ?? "No date yet",
    tone: "mint",
    description: "Open the job to review its live details and timeline.",
  };
}
