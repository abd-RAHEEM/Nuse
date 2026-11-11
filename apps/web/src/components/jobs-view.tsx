"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { api, apiMode, ApiError } from "@/lib/api/client";
import type { GmailReviewItem, JobDetail, JobStatus, JobSummary } from "@/types/api";
import { CalendarEventDialog } from "@/components/calendar-event-dialog";
import { Icon } from "./nuse-shell";

type Job = { id?: string; company: string; initials: string; title: string; location: string; status: string; applied: string; followUp: string; tone: string; description: string };
const statuses = ["All", "Saved", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn", "On hold"];
const gmailReviewStatuses: JobStatus[] = [
  "applied",
  "assessment",
  "interview",
  "offer",
  "rejected",
];

function isGmailReviewStatus(value: string): value is JobStatus {
  return gmailReviewStatuses.some((status) => status === value);
}
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

function JobCard({
  job,
  expanded,
  onToggle,
  onAdvance,
  onArchive,
  onDelete,
}: {
  job: Job;
  expanded: boolean;
  onToggle: () => void;
  onAdvance: () => void;
  onArchive: () => void;
  onDelete: () => void;
}) {
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    if (!expanded || !job.id) return;
    let active = true;
    void api.jobs
      .get(job.id)
      .then((result) => {
        if (active) {
          setDetail(result);
          setDetailError("");
        }
      })
      .catch(() => {
        if (active) setDetailError("Job details could not be loaded. Open the full record to retry.");
      });
    return () => {
      active = false;
    };
  }, [expanded, job.id, job.status]);

  return (
    <article className={`job-card ${expanded ? "expanded" : ""}`}>
      <button className="job-summary" onClick={onToggle} aria-expanded={expanded}>
        <span className={`company-mark ${job.tone}`}>{job.initials}</span>
        <span className="job-title-block">
          <strong>{job.title}</strong>
          <small>{job.company} · {job.location}</small>
        </span>
        <span className="job-status">
          <StageRail status={job.status} />
          <b>{job.status}</b>
        </span>
        <span className="job-follow">
          <small>Next action</small>
          <strong>{job.followUp}</strong>
        </span>
        <span className="expand-control">
          {expanded ? "Collapse" : "Details"}{" "}
          <span className={expanded ? "rotated" : ""}>⌄</span>
        </span>
      </button>
      {expanded && job.id && (
        <div className="job-expansion">
          {detailError ? (
            <p className="page-support" role="alert">{detailError}</p>
          ) : detail ? (
            <LiveJobExpansion
              detail={detail}
              onAdvance={onAdvance}
              onArchive={onArchive}
              onDelete={onDelete}
              onCalendarSaved={(eventId) => {
                if (!eventId) return;
                setDetail((current) => current && ({
                  ...current,
                  timeline: current.timeline.map((event) =>
                    event.id === eventId ? { ...event, calendarLinked: true } : event,
                  ),
                }));
              }}
              onTimelineUpdated={(updatedEvent) => {
                setDetail((current) => current && ({
                  ...current,
                  timeline: current.timeline.map((event) =>
                    event.id === updatedEvent.id ? updatedEvent : event,
                  ),
                }));
              }}
            />
          ) : (
            <p className="page-support">Loading job details…</p>
          )}
        </div>
      )}
      {expanded && !job.id && (
        <div className="job-expansion">
          <div className="job-analysis">
            <div className="analysis-main">
              <div className="analysis-heading">
                <span className="eyebrow">Full analysis</span>
                <span className="source-chip">
                  kite.systems <Icon name="external" size={12} />
                </span>
              </div>
              <p>{job.description}</p>
              <div className="analysis-section">
                <span className="eyebrow">Why it fits</span>
                <p className="analysis-copy">
                  Strong overlap with your ML platform work, Python systems experience, and interest in reliable production tooling.
                </p>
              </div>
              <div className="analysis-facts">
                <span><small>Application date</small><strong>{job.applied}</strong></span>
                <span><small>Work mode</small><strong>{job.location.split("·")[1]?.trim()}</strong></span>
                <span><small>Source</small><strong>Company careers</strong></span>
                <span><small>Signal</small><strong className="signal">High alignment</strong></span>
              </div>
              <div className="analysis-tags">
                <span>Python</span><span>Machine learning</span><span>Platform</span>
              </div>
              <div className="analysis-actions">
                <button className="primary-button small" onClick={onAdvance}>
                  Mark as next stage <Icon name="arrow" size={14} />
                </button>
                <Link className="quiet-button small" href="/jobs">Open full record</Link>
                <button className="quiet-button small" onClick={onArchive}>Archive</button>
                <button className="quiet-button small" onClick={onDelete}>Delete</button>
              </div>
            </div>
            <div className="analysis-side">
              <span className="eyebrow">Personal note</span>
              <p>Prepare two examples that show calm ownership when the requirements are still moving.</p>
              <button className="text-button">Edit note <Icon name="arrow" size={13} /></button>
              <div className="analysis-side-block">
                <span className="eyebrow">Requirements</span>
                <ul>
                  <li>Production Python experience</li>
                  <li>Comfort with ambiguous systems</li>
                  <li>Clear written communication</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="job-timeline">
            <div className="timeline-header">
              <span className="eyebrow">Application timeline</span>
              <button className="text-button">
                Add event <Icon name="plus" size={13} />
              </button>
            </div>
            <div className="timeline-track">
              <div className="timeline-progress" />
              <TimelineEvent date="Nov 01" title="Job saved" detail="Found through company careers" />
              <TimelineEvent
                date={job.applied.replace(", 2026", "")}
                title="Applied"
                detail="Resume and portfolio submitted"
                filled
              />
              <TimelineEvent
                date={job.status === "Interview" ? "Nov 05" : "Next"}
                title={job.status === "Interview" ? "Technical interview" : "Next follow-up"}
                detail={job.status === "Interview" ? "Scheduled · 45 minutes" : "Keep the application moving"}
                scheduled={job.status !== "Interview"}
              />
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function LiveJobExpansion({
  detail,
  onAdvance,
  onArchive,
  onDelete,
  onCalendarSaved,
  onTimelineUpdated,
}: {
  detail: JobDetail;
  onAdvance: () => void;
  onArchive: () => void;
  onDelete: () => void;
  onCalendarSaved: (eventId?: string) => void;
  onTimelineUpdated: (event: JobDetail["timeline"][number]) => void;
}) {
  const [calendarOpen, setCalendarOpen] = useState(false);
  const eventDate = (value: string) =>
    new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short" }).format(
      new Date(value),
    );

  return (
    <>
      <div className="job-analysis">
        <div className="analysis-main">
          <div className="analysis-heading">
            <span className="eyebrow">Job details</span>
            {detail.sourceUrl && (
              <a
                className="source-chip"
                href={detail.sourceUrl}
                target="_blank"
                rel="noreferrer"
              >
                Original source <Icon name="external" size={12} />
              </a>
            )}
          </div>
          <p>{detail.description || "No description was saved for this job."}</p>
          <div className="analysis-facts">
            <span>
              <small>Application date</small>
              <strong>{detail.appliedOn ?? "Not applied"}</strong>
            </span>
            <span>
              <small>Work mode</small>
              <strong>{detail.workMode ?? "Not specified"}</strong>
            </span>
            <span>
              <small>Employment type</small>
              <strong>{detail.employmentType?.replaceAll("_", " ") ?? "Not specified"}</strong>
            </span>
            <span>
              <small>Deadline</small>
              <strong>{detail.deadline ?? "No deadline set"}</strong>
            </span>
          </div>
          {detail.tags.length > 0 && (
            <div className="analysis-tags">
              {detail.tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}
            </div>
          )}
          <div className="analysis-actions">
            <button className="primary-button small" onClick={onAdvance}>
              Mark as next stage <Icon name="arrow" size={14} />
            </button>
            <Link className="quiet-button small" href={`/jobs/${detail.id}`}>
              Open full record
            </Link>
            <button className="quiet-button small" onClick={onArchive}>Archive</button>
            <button className="quiet-button small" onClick={onDelete}>Delete</button>
          </div>
        </div>
        <div className="analysis-side">
          <span className="eyebrow">Personal note</span>
          <p>{detail.notes || "No notes added yet."}</p>
          <Link className="text-button" href={`/jobs/${detail.id}`}>
            Edit job details <Icon name="arrow" size={13} />
          </Link>
          <div className="analysis-side-block">
            <span className="eyebrow">Requirements</span>
            <p>{detail.requirements || "No requirements listed."}</p>
          </div>
        </div>
      </div>
      <div className="job-timeline">
        <div className="timeline-header">
          <span className="eyebrow">Job timeline</span>
          <div className="timeline-actions">
            <button className="text-button" onClick={() => setCalendarOpen(true)}>
              Add to calendar
            </button>
            <Link className="text-button" href={`/jobs/${detail.id}`}>
              Open timeline <Icon name="arrow" size={13} />
            </Link>
          </div>
        </div>
        {detail.timeline.length > 0 ? (
          <div className="timeline-track">
            <div className="timeline-progress" />
            {detail.timeline.map((event) => (
              <TimelineEvent
                key={event.id}
                date={eventDate(event.scheduledFor ?? event.occurredAt)}
                title={event.title}
                detail={event.notes ?? event.type.replaceAll("_", " ")}
                filled={event.type === "saved" || event.type === "applied"}
                scheduled={Boolean(event.scheduledFor && new Date(event.scheduledFor) > new Date())}
              />
            ))}
          </div>
        ) : (
          <p className="page-support">No events have been added to this job.</p>
        )}
      </div>
      {calendarOpen && (
        <CalendarEventDialog
          job={detail}
          onClose={() => setCalendarOpen(false)}
          onSaved={onCalendarSaved}
          onTimelineUpdated={onTimelineUpdated}
        />
      )}
    </>
  );
}

function TimelineEvent({ date, title, detail, filled = false, scheduled = false }: { date: string; title: string; detail: string; filled?: boolean; scheduled?: boolean }) {
  return <div className={`timeline-event ${scheduled ? "scheduled" : ""}`}><span className={`event-marker ${filled ? "filled" : ""}`} /><span className="timeline-event-copy"><time>{date}</time><strong>{title}</strong><small>{detail}</small></span></div>;
}

function JobsAnalytics({
  jobs,
  onSelectStage,
}: {
  jobs: Job[];
  onSelectStage: (stage: string) => void;
}) {
  const stages = [
    { label: "Saved", tone: "saved" },
    { label: "Applied", tone: "applied" },
    { label: "Assessment", tone: "assessment" },
    { label: "Interview", tone: "interview" },
    { label: "Offer", tone: "offer" },
  ].map((stage) => ({
    ...stage,
    count: jobs.filter((job) => job.status === stage.label).length,
  }));
  const interviews = stages.find((stage) => stage.label === "Interview")?.count ?? 0;
  const followUps = jobs.filter((job) => job.followUp !== "No date yet").length;
  const onHold = jobs.filter((job) => job.status === "On hold").length;

  return <section className="jobs-analytics" aria-labelledby="analytics-title">
    <div className="analytics-heading"><div><p className="eyebrow">A clear view of the pipeline</p><h2 id="analytics-title">Your applications, at a glance.</h2></div><span className="analytics-updated">Current view</span></div>
    <div className="analytics-grid">
      <div className="pipeline-panel"><div className="analytics-label-row"><span className="eyebrow">Pipeline shape</span><span className="analytics-total">{jobs.length} records</span></div><div className="pipeline-bars">{stages.map((stage) => <button className="pipeline-stage" key={stage.label} onClick={() => onSelectStage(stage.label)}><span className={`pipeline-bar ${stage.tone}`} style={{ "--bar-size": `${Math.max(stage.count * 12, 4)}%` } as CSSProperties} /><span><b>{stage.count}</b><small>{stage.label}</small></span></button>)}</div></div>
      <div className="analytics-stat stat-mint"><span className="eyebrow">At interview stage</span><strong>{interviews}</strong><small>Jobs currently in interview</small></div>
      <div className="analytics-stat stat-amber"><span className="eyebrow">Follow-ups set</span><strong>{followUps}</strong><small>Jobs with a next action date</small></div>
      <div className="analytics-stat stat-lavender"><span className="eyebrow">On hold</span><strong>{onHold}</strong><small>Paused applications</small></div>
    </div>
  </section>;
}

function GmailReviewQueue({ onResolved }: { onResolved: () => void }) {
  const [items, setItems] = useState<GmailReviewItem[]>([]);
  const [selectedStages, setSelectedStages] = useState<Record<string, JobStatus>>({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");

  useEffect(() => {
    if (apiMode !== "live") return;
    let active = true;
    void api.integrations.gmailReviews()
      .then(({ items: reviews }) => {
        if (active) {
          setItems(reviews);
          setMessage("");
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof ApiError
              ? error.message
              : "Matched Gmail messages could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const resolve = async (
    item: GmailReviewItem,
    decision: JobStatus | "ignore",
  ) => {
    setWorkingId(item.messageId);
    setMessage("");
    try {
      await api.integrations.resolveGmailReview(item.messageId, decision);
      setItems((current) => current.filter((entry) => entry.messageId !== item.messageId));
      onResolved();
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "This email update could not be saved. Try again.",
      );
    } finally {
      setWorkingId("");
    }
  };

  if (loading || (items.length === 0 && !message)) return null;
  return (
    <section className="gmail-review-panel" aria-labelledby="gmail-review-title">
      <div className="gmail-review-heading">
        <div>
          <p className="eyebrow">Matched to saved jobs</p>
          <h2 id="gmail-review-title">Email updates to review</h2>
        </div>
        <span>{items.length}</span>
      </div>
      {message && <p className="gmail-review-error" role="alert">{message}</p>}
      {items.map((item) => {
        const selected = selectedStages[item.messageId] ?? item.suggestedStatus ?? "";
        return (
          <article className="gmail-review-item" key={item.messageId}>
            <div className="gmail-review-copy">
              <Link href={`/jobs/${item.jobId}`}><strong>{item.title}</strong></Link>
              <small>{item.company} {item.sender ? ` · ${item.sender}` : ""}</small>
              <span>{item.subject}</span>
              <time dateTime={item.receivedAt}>
                {new Date(item.receivedAt).toLocaleString("en-IN")}
              </time>
            </div>
            <div className="gmail-review-actions">
              <label>
                <span className="sr-only">Application stage from this email</span>
                <select
                  aria-label="Application stage from this email"
                  value={selected}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (isGmailReviewStatus(value)) {
                      setSelectedStages((current) => ({
                        ...current,
                        [item.messageId]: value,
                      }));
                    }
                  }}
                  disabled={workingId === item.messageId}
                >
                  <option value="">Choose a stage</option>
                  {gmailReviewStatuses.map((stage) => (
                    <option value={stage} key={stage}>
                      {stage.charAt(0).toUpperCase() + stage.slice(1)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  if (selected) void resolve(item, selected);
                }}
                disabled={!selected || workingId === item.messageId}
              >
                Apply update
              </button>
              <button
                className="quiet-button"
                type="button"
                onClick={() => void resolve(item, "ignore")}
                disabled={workingId === item.messageId}
              >
                Ignore
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
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
  const [sort, setSort] = useState<"newest" | "oldest" | "next_action">("newest");
  const [appliedFrom, setAppliedFrom] = useState("");
  const [appliedTo, setAppliedTo] = useState("");
  const [followUpBefore, setFollowUpBefore] = useState("");
  const [archivedOnly, setArchivedOnly] = useState(false);
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);
  const [filtersReady, setFiltersReady] = useState(false);
  const [gmailUpdateRevision, setGmailUpdateRevision] = useState(0);
  useEffect(() => {
    const restoreFilters = () => {
      const params = new URLSearchParams(window.location.search);
      const rawStatus = (params.get("status[]") ?? params.get("status"))?.replaceAll("_", " ");
      const selectedStatus = statuses.find(
        (item) => item.toLowerCase() === rawStatus?.toLowerCase(),
      ) ?? "All";
      const requestedSort = params.get("sort");
      setQuery(params.get("q") ?? "");
      setStatus(selectedStatus);
      setLocation(params.get("location") ?? "All locations");
      setAppliedFrom(params.get("appliedFrom") ?? "");
      setAppliedTo(params.get("appliedTo") ?? "");
      setFollowUpBefore(params.get("followUpBefore") ?? "");
      setArchivedOnly(params.get("archived") === "true");
      setSort(
        requestedSort === "oldest" || requestedSort === "next_action"
          ? requestedSort
          : "newest",
      );
      setFiltersReady(true);
    };
    restoreFilters();
    window.addEventListener("popstate", restoreFilters);
    return () => window.removeEventListener("popstate", restoreFilters);
  }, []);
  useEffect(() => {
    if (!filtersReady) return;
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (status !== "All") params.set("status[]", status.toLowerCase().replaceAll(" ", "_"));
    if (location !== "All locations") params.set("location", location);
    if (appliedFrom) params.set("appliedFrom", appliedFrom);
    if (appliedTo) params.set("appliedTo", appliedTo);
    if (followUpBefore) params.set("followUpBefore", followUpBefore);
    if (archivedOnly) params.set("archived", "true");
    if (sort !== "newest") params.set("sort", sort);
    const search = params.toString();
    const url = `/jobs${search ? `?${search}` : ""}`;
    const timer = window.setTimeout(() => {
      if (`${window.location.pathname}${window.location.search}` !== url) {
        window.history.pushState(null, "", url);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [filtersReady, query, status, location, appliedFrom, appliedTo, followUpBefore, archivedOnly, sort]);
  useEffect(() => {
    if (apiMode !== "live" || !filtersReady) return;
    let active = true;
    api.jobs.list({
      q: query || undefined,
      status: status === "All" ? undefined : [status.toLowerCase().replaceAll(" ", "_")],
      location: location === "All locations" ? undefined : location,
      appliedFrom: appliedFrom || undefined,
      appliedTo: appliedTo || undefined,
      followUpBefore: followUpBefore || undefined,
      archived: archivedOnly,
      sort,
      limit: 100,
    }).then((result) => {
      if (active) {
        setLiveJobs(result.items.map(toDisplayJob));
        setLiveError("");
      }
    }).catch(() => {
      if (active) setLiveError("The live jobs ledger could not be loaded. Check that the API is running.");
    });
    return () => { active = false; };
  }, [filtersReady, query, status, location, appliedFrom, appliedTo, followUpBefore, archivedOnly, sort, gmailUpdateRevision]);
  const sourceJobs = apiMode === "live" ? liveJobs ?? [] : jobs;
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
  return (
    <div className="jobs-stack">
      <GmailReviewQueue onResolved={() => setGmailUpdateRevision((value) => value + 1)} />
      <JobsAnalytics jobs={visible} onSelectStage={setStatus} />
      <div className="page-intro-row">
        <div>
          <p className="eyebrow">The application ledger</p>
          <p className="page-support">
            {liveError ||
              (apiMode === "live"
                ? liveJobs === null
                  ? "Loading your jobs…"
                  : `${liveJobs.length} records in this view`
                : `${visible.length} records in this view`)}
          </p>
        </div>
        <div className="view-actions">
          <button
            className={`quiet-button ${moreFiltersOpen ? "active" : ""}`}
            onClick={() => setMoreFiltersOpen((open) => !open)}
            aria-expanded={moreFiltersOpen}
          >
            <Icon name="sliders" size={15} /> More filters
          </button>
          <button className="primary-button" onClick={() => setAddOpen(true)}>
            <Icon name="plus" size={15} /> Add job
          </button>
        </div>
      </div>
      <div className="job-filter-panel">
        <div className="filter-heading">
          <span className="eyebrow">Filter and find</span>
          <span className="filter-count">{visible.length} visible</span>
        </div>
        <div className="filter-controls">
          <label className="search-field">
            <span>/</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search role or company"
            />
          </label>
          <div className="filter-pills">
            {statuses.map((item) => (
              <button
                key={item}
                className={status === item ? "active" : ""}
                onClick={() => setStatus(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <select
            className="location-select"
            value={location}
            onChange={(event) => setLocation(event.target.value)}
            aria-label="Filter by location"
          >
            <option>All locations</option>
            <option>Remote</option>
            <option>Hybrid</option>
            <option>On-site</option>
          </select>
        </div>
        {moreFiltersOpen && (
          <div className="advanced-job-filters">
            <label>
              Applied from
              <input
                type="date"
                value={appliedFrom}
                onChange={(event) => setAppliedFrom(event.target.value)}
              />
            </label>
            <label>
              Applied through
              <input
                type="date"
                value={appliedTo}
                onChange={(event) => setAppliedTo(event.target.value)}
              />
            </label>
            <label>
              Follow-up by
              <input
                type="date"
                value={followUpBefore}
                onChange={(event) => setFollowUpBefore(event.target.value)}
              />
            </label>
            <label className="archived-filter">
              <input
                type="checkbox"
                checked={archivedOnly}
                onChange={(event) => setArchivedOnly(event.target.checked)}
              />{" "}
              Archived jobs only
            </label>
          </div>
        )}
      </div>
      <div className="jobs-toolbar">
        <div className="toolbar-tabs">
          <button className="active">Cards</button>
          <button>Board</button>
        </div>
        <label className="sort-control">
          <span>Sort by</span>
          <select
            className="sort-button"
            value={sort}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "newest" || value === "oldest" || value === "next_action") {
                setSort(value);
              }
            }}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="next_action">Next action</option>
          </select>
        </label>
      </div>
      <div className="jobs-list">
        {visible.map((job) => {
          const key = job.id ?? job.title;
          const isExpanded = expanded.has(key);
          return (
            <JobCard
              key={key}
              job={job}
              expanded={isExpanded}
              onAdvance={() => mutateJob(job, "advance")}
              onArchive={() => mutateJob(job, "archive")}
              onDelete={() => mutateJob(job, "delete")}
              onToggle={() =>
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(key)) next.delete(key);
                  else next.add(key);
                  return next;
                })
              }
            />
          );
        })}
      </div>
      {addOpen && (
        <div
          className="sheet-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setAddOpen(false);
          }}
        >
          <section
            className="capture-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-job-title"
          >
            <div className="sheet-grip" />
            <div className="sheet-header">
              <div>
                <p className="eyebrow">Add a record</p>
                <h2 id="add-job-title">Save a job to the desk.</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setAddOpen(false)}
                aria-label="Close add job"
              >
                ×
              </button>
            </div>
            <form className="auth-form" onSubmit={saveJob}>
              <label>
                Company
                <input
                  value={newCompany}
                  onChange={(event) => setNewCompany(event.target.value)}
                  required
                />
              </label>
              <label>
                Role title
                <input
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                  required
                />
              </label>
              <label>
                Location
                <input
                  value={newLocation}
                  onChange={(event) => setNewLocation(event.target.value)}
                  placeholder="Remote, Bengaluru, or leave blank"
                />
              </label>
              <label>
                Source URL
                <input
                  type="url"
                  value={newUrl}
                  onChange={(event) => setNewUrl(event.target.value)}
                  placeholder="https://..."
                />
              </label>
              <button className="primary-button wide" type="submit" disabled={saving}>
                {saving ? "Saving job…" : "Save job"} <Icon name="arrow" size={15} />
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function toDisplayJob(job: JobSummary): Job {
  const status = job.status.replaceAll("_", " ");
  return {
    id: job.id,
    company: job.company,
    initials: job.company.slice(0, 2).toUpperCase(),
    title: job.title,
    location: [
      job.location,
      job.workMode === "onsite"
        ? "On-site"
        : job.workMode
          ? job.workMode.charAt(0).toUpperCase() + job.workMode.slice(1)
          : null,
    ].filter(Boolean).join(" · ") || "Location not listed",
    status: status.charAt(0).toUpperCase() + status.slice(1),
    applied: job.appliedOn ?? "Not applied",
    followUp: job.nextFollowUpOn ?? "No date yet",
    tone: "mint",
    description: "Open the job to review its live details and timeline.",
  };
}
