"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { NuseShell, Icon } from "@/components/nuse-shell";
import { api, apiMode } from "@/lib/api/client";
import type { JobDetail } from "@/types/api";

export default function JobDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState("");
  const [eventTitle, setEventTitle] = useState("");
  const [eventType, setEventType] = useState<"interview" | "assessment" | "follow_up" | "note">("note");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [eventScheduledFor, setEventScheduledFor] = useState("");
  const [addToCalendar, setAddToCalendar] = useState(false);

  useEffect(() => {
    if (apiMode !== "live") return;
    api.jobs.get(id).then((loaded) => {
      setJob(loaded);
      setNotes(loaded.notes ?? "");
    }).catch(() => setError("This job could not be found."));
    api.integrations.list().then(({ items }) => {
      setCalendarConnected(items.some(
        (item) => item.provider === "google_calendar"
          && item.status === "connected"
          && Boolean(item.config.calendarId),
      ));
    }).catch(() => setError("The calendar connection status could not be checked."));
  }, [id]);

  const saveNotes = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!job) return;
    setSaving(true);
    try {
      const updated = await api.jobs.update(job.id, { notes });
      setJob(updated);
    } catch {
      setError("The job notes could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const addEvent = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!job || !eventTitle.trim()) return;
    try {
      const scheduledFor = eventScheduledFor
        ? new Date(eventScheduledFor).toISOString()
        : undefined;
      const created = await api.jobs.createEvent(job.id, {
        type: eventType,
        title: eventTitle.trim(),
        scheduledFor,
      });
      setJob({ ...job, timeline: [...job.timeline, created] });
      setEventTitle("");
      setEventScheduledFor("");
      if (addToCalendar && scheduledFor) {
        try {
          await api.integrations.createCalendarEvent({
            jobId: job.id,
            jobEventId: created.id,
            startsAt: scheduledFor,
            endsAt: new Date(new Date(scheduledFor).getTime() + 60 * 60 * 1000).toISOString(),
            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          });
          setJob((current) => current && ({
            ...current,
            timeline: current.timeline.map((item) => item.id === created.id
              ? { ...item, calendarLinked: true }
              : item),
          }));
        } catch {
          setError("The timeline event was saved, but Google Calendar could not be updated. Retry from the event below.");
        }
      }
      setAddToCalendar(false);
    } catch {
      setError("The event could not be added.");
    }
  };

  const syncEventToCalendar = async (item: JobDetail["timeline"][number]) => {
    if (!job || !item.scheduledFor) return;
    try {
      await api.integrations.createCalendarEvent({
        jobId: job.id,
        jobEventId: item.id,
        title: item.title,
        startsAt: item.scheduledFor,
        endsAt: new Date(new Date(item.scheduledFor).getTime() + 60 * 60 * 1000).toISOString(),
        allDay: item.allDay,
        timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      setJob((current) => current && ({
        ...current,
        timeline: current.timeline.map((event) => event.id === item.id
          ? { ...event, calendarLinked: true }
          : event),
      }));
      setError("");
    } catch {
      setError("Google Calendar could not be updated. Check the connection and try again.");
    }
  };

  const archiveJob = async () => {
    if (!job || !window.confirm(job.archived ? "Restore this job to the active ledger?" : "Archive this job?")) return;
    setActionBusy(true);
    try {
      const updated = await api.jobs.update(job.id, { archived: !job.archived });
      setJob(updated);
    } catch {
      setError(job.archived ? "The job could not be restored." : "The job could not be archived.");
    } finally {
      setActionBusy(false);
    }
  };

  const deleteJob = async () => {
    if (!job || !window.confirm("Delete this job and its timeline permanently?")) return;
    setActionBusy(true);
    try {
      await api.jobs.remove(job.id);
      router.push("/jobs");
    } catch {
      setError("The job could not be deleted.");
      setActionBusy(false);
    }
  };

  if (apiMode !== "live") {
    return <NuseShell title="Job detail" eyebrow="Mock mode"><DetailUnavailable /></NuseShell>;
  }
  return <NuseShell title={job?.title ?? "Job detail"} eyebrow={job?.company ?? "Live record"}><div className="detail-page">
    <Link href="/jobs" className="text-button"><Icon name="arrow" size={13} /> Back to jobs</Link>
    {error && <p className="auth-error" role="alert">{error}</p>}
    {job && <><div className="detail-hero"><span className="company-mark mint">{job.company.slice(0, 2).toUpperCase()}</span><div><p className="eyebrow">{job.company}</p><h2>{job.title}</h2><p>{job.location ?? "Location not listed"} · {job.workMode ?? "Work mode not listed"}</p></div><span className="source-chip">{job.archived ? "Archived" : job.status}</span></div><div className="detail-grid"><section className="detail-panel"><p className="eyebrow">Description</p><p className="detail-copy">{job.description ?? "No description has been added yet."}</p><p className="eyebrow">Requirements</p><p className="detail-copy">{job.requirements ?? "No requirements have been added yet."}</p><form className="detail-edit-form" onSubmit={saveNotes}><label><span className="eyebrow">Personal notes</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Keep the next useful thought here." rows={5} /></label><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save notes"} <Icon name="check" size={14} /></button></form></section><aside className="detail-panel"><p className="eyebrow">Application facts</p><dl className="detail-facts"><div><dt>Applied</dt><dd>{job.appliedOn ?? "Not applied"}</dd></div><div><dt>Next follow-up</dt><dd>{job.nextFollowUpOn ?? "Not scheduled"}</dd></div><div><dt>Source</dt><dd>{job.sourceUrl ? <a href={job.sourceUrl} target="_blank" rel="noreferrer">Open source</a> : "Not listed"}</dd></div></dl><div className="detail-actions"><button className="secondary-button" type="button" onClick={archiveJob} disabled={actionBusy}>{job.archived ? "Restore job" : "Archive job"}</button><button className="danger-button" type="button" onClick={deleteJob} disabled={actionBusy}>Delete job</button></div></aside></div><section className="detail-panel detail-timeline"><div className="section-heading"><div><p className="eyebrow">Application timeline</p><h3>What has happened</h3></div></div><div className="activity-line detail-events">{job.timeline.map((item) => <div className="activity-item" key={item.id}><span className="timeline-dot filled" /><span><strong>{item.title}</strong><small>{new Date(item.scheduledFor ?? item.occurredAt).toLocaleString("en-IN")}{item.calendarLinked ? " · In Google Calendar" : ""}</small>{calendarConnected && item.scheduledFor && <button className="text-button" type="button" disabled={item.calendarLinked} onClick={() => void syncEventToCalendar(item)}>{item.calendarLinked ? "Added to calendar" : "Add to Google Calendar"}</button>}</span></div>)}</div><form className="detail-event-form" onSubmit={addEvent}><select value={eventType} onChange={(event) => setEventType(event.target.value as typeof eventType)} aria-label="Event type"><option value="note">Note</option><option value="interview">Interview</option><option value="assessment">Assessment</option><option value="follow_up">Follow-up</option></select><input value={eventTitle} onChange={(event) => setEventTitle(event.target.value)} placeholder="Add a timeline event" required /><input type="datetime-local" value={eventScheduledFor} onChange={(event) => setEventScheduledFor(event.target.value)} aria-label="Schedule event date and time" />{calendarConnected && <label><input type="checkbox" checked={addToCalendar} onChange={(event) => setAddToCalendar(event.target.checked)} /> Add to Google Calendar</label>}<button className="primary-button" type="submit" disabled={addToCalendar && !eventScheduledFor}>Add event <Icon name="plus" size={14} /></button></form></section></>}
  </div></NuseShell>;
}

function DetailUnavailable() {
  return <div className="detail-empty"><p className="eyebrow">Mock mode</p><h2>Open a live record from the Jobs ledger.</h2><Link href="/jobs" className="primary-button">Back to jobs <Icon name="arrow" size={14} /></Link></div>;
}
