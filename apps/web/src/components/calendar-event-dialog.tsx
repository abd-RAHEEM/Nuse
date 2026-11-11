"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api/client";
import type { JobDetail } from "@/types/api";

type JobContext = Pick<JobDetail, "id" | "title" | "company" | "sourceUrl" | "timeline">;

function formatDateTime(date: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

const localInputValue = (date: Date) =>
  formatDateTime(date, Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");

function localValueInZone(value: string, timeZone: string): string {
  const [datePart, timePart] = value.split("T");
  if (!datePart || !timePart) throw new Error("Choose a valid date and time.");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  let timestamp = Date.UTC(year, month - 1, day, hour, minute);

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(timestamp));
    const values = Object.fromEntries(parts.map((part) => [part.type, Number(part.value)]));
    const renderedAsUtc = Date.UTC(
      values.year,
      values.month - 1,
      values.day,
      values.hour,
      values.minute,
    );
    const desiredAsUtc = Date.UTC(year, month - 1, day, hour, minute);
    const difference = desiredAsUtc - renderedAsUtc;
    if (difference === 0) break;
    timestamp += difference;
  }

  if (formatDateTime(new Date(timestamp), timeZone) !== value) {
    throw new Error("That local time does not exist because of a daylight-saving change.");
  }
  return new Date(timestamp).toISOString();
}

function addMinutes(value: string, minutes: number): string {
  return localInputValue(new Date(new Date(value).getTime() + minutes * 60_000));
}

function eventInputValue(scheduledFor: string | null, timeZone: string): string {
  if (!scheduledFor) return "";
  return formatDateTime(new Date(scheduledFor), timeZone);
}

export function CalendarEventDialog({
  onClose,
  job,
  initialEventId,
  onSaved,
  onTimelineUpdated,
}: {
  onClose: () => void;
  job?: JobContext;
  initialEventId?: string;
  onSaved?: (timelineEventId?: string) => void;
  onTimelineUpdated?: (event: JobDetail["timeline"][number]) => void;
}) {
  const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const initialEvent = job?.timeline.find((event) => event.id === initialEventId);
  const initialScheduledFor = initialEvent?.scheduledFor ?? null;
  const initialAllDay = initialEvent?.allDay ?? false;
  const initialStart = initialEvent
    ? eventInputValue(initialScheduledFor, browserTimeZone)
    : "";
  const [title, setTitle] = useState(initialEvent?.title ?? (job ? `${job.title} — ${job.company}` : ""));
  const [description, setDescription] = useState(
    initialEvent ? initialEvent.notes ?? "" : job?.sourceUrl ?? "",
  );
  const [location, setLocation] = useState("");
  const [timeZone, setTimeZone] = useState(browserTimeZone);
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(() => initialEvent?.allDay
    ? initialStart
    : initialEvent
      ? addMinutes(initialStart, 60)
      : "");
  const [allDay, setAllDay] = useState(initialEvent?.allDay ?? false);
  const [reminder, setReminder] = useState("10");
  const [selectedEventId, setSelectedEventId] = useState(initialEventId ?? "");
  const [saving, setSaving] = useState(false);
  const [formReady, setFormReady] = useState(false);
  const [message, setMessage] = useState("");
  const [createdUrl, setCreatedUrl] = useState("");
  const [saved, setSaved] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    let active = true;
    void api.settings.get()
      .then((settings) => {
        if (!active) return;
        setTimeZone(settings.timezone);
        if (initialScheduledFor) {
          const eventStart = eventInputValue(initialScheduledFor, settings.timezone);
          setStart(eventStart);
          setEnd(initialAllDay ? eventStart : addMinutes(eventStart, 60));
        } else {
          const now = Date.now();
          setStart(formatDateTime(new Date(now + 60 * 60_000), settings.timezone));
          setEnd(formatDateTime(new Date(now + 2 * 60 * 60_000), settings.timezone));
        }
        setFormReady(true);
      })
      .catch(() => {
        if (!active) return;
        const now = Date.now();
        setStart(initialScheduledFor
          ? eventInputValue(initialScheduledFor, browserTimeZone)
          : formatDateTime(new Date(now + 60 * 60_000), browserTimeZone));
        setEnd(initialScheduledFor
          ? initialAllDay
            ? eventInputValue(initialScheduledFor, browserTimeZone)
            : addMinutes(eventInputValue(initialScheduledFor, browserTimeZone), 60)
          : formatDateTime(new Date(now + 2 * 60 * 60_000), browserTimeZone));
        setFormReady(true);
        setMessage("Could not load your saved timezone. Using this device’s timezone.");
      });
    return () => { active = false; };
  }, [
    browserTimeZone,
    initialAllDay,
    initialScheduledFor,
  ]);

  const scheduledEvents = job?.timeline.filter((event) => event.scheduledFor) ?? [];

  const selectTimelineEvent = (id: string) => {
    setSelectedEventId(id);
    const event = scheduledEvents.find((item) => item.id === id);
    if (!event?.scheduledFor) {
      setTitle(job ? `${job.title} — ${job.company}` : "");
      setDescription(job?.sourceUrl ?? "");
      setAllDay(false);
      return;
    }
    const eventStart = eventInputValue(event.scheduledFor, timeZone);
    setTitle(event.title);
    setDescription(event.notes ?? "");
    setAllDay(event.allDay);
    setStart(eventStart);
    setEnd(event.allDay ? eventStart : addMinutes(eventStart, 60));
  };

  const save = async (formEvent: FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    setSaving(true);
    setMessage("");
    setCreatedUrl("");
    setSaved(false);
    setNeedsSetup(false);
    try {
      const startValue = allDay ? `${start.slice(0, 10)}T00:00:00` : start;
      const endValue = end
        ? allDay
          ? `${end.slice(0, 10)}T00:00:00`
          : end
        : undefined;
      const startsAt = allDay
        ? `${startValue}+00:00`
        : localValueInZone(startValue, timeZone);
      const endsAt = endValue
        ? allDay
          ? `${endValue}+00:00`
          : localValueInZone(endValue, timeZone)
        : undefined;
      if (selectedEventId && job) {
        const updatedEvent = await api.jobs.updateEvent(job.id, selectedEventId, {
          title: title.trim(),
          notes: description.trim() || null,
          scheduledFor: startsAt,
          allDay,
        });
        onTimelineUpdated?.(updatedEvent);
      }
      const result = await api.integrations.createCalendarEvent({
        jobId: job?.id,
        jobEventId: selectedEventId || undefined,
        title: title.trim(),
        description: description.trim(),
        location: location.trim(),
        startsAt,
        endsAt,
        allDay,
        timeZone,
        reminders: reminder ? [{ method: "popup", minutes: Number(reminder) }] : [],
      });
      setCreatedUrl(result.htmlLink ?? "");
      setSaved(true);
      setMessage("Event saved to Google Calendar.");
      onSaved?.(selectedEventId || undefined);
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : error instanceof Error
            ? error.message
            : "The event could not be saved.",
      );
      setNeedsSetup(error instanceof ApiError && error.status === 409);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="calendar-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <section
        className="calendar-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="calendar-modal-title"
      >
        <div className="calendar-modal-heading">
          <div>
            <p className="eyebrow">Google Calendar</p>
            <h2 id="calendar-modal-title">Review this event</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close calendar event form">
            ×
          </button>
        </div>
        {message && (
          <p className={createdUrl || message.startsWith("Event saved") ? "calendar-result" : "calendar-error"} role="status">
            {message}
            {createdUrl && (
              <>{" "}<a href={createdUrl} target="_blank" rel="noreferrer">Open event</a></>
            )}
            {needsSetup && <>{" "}<Link href="/settings">Connect Google Calendar in Settings</Link>.</>}
          </p>
        )}
        {scheduledEvents.length > 0 && (
          <label className="calendar-field">
            Start from a job timeline event
            <select
              value={selectedEventId}
              onChange={(event) => selectTimelineEvent(event.target.value)}
            >
              <option value="">Create a separate event</option>
              {scheduledEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title} — {new Intl.DateTimeFormat("en-SG", {
                    dateStyle: "medium",
                    timeStyle: event.allDay ? undefined : "short",
                    timeZone,
                  }).format(new Date(event.scheduledFor ?? ""))}
                </option>
              ))}
            </select>
          </label>
        )}
        <form className="calendar-form" onSubmit={save}>
          <label className="calendar-field">
            Event title
            <input
              required
              maxLength={selectedEventId ? 200 : 1024}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <div className="calendar-timezone">
            <label className="calendar-field">
              Starts
              <input
                required
                type={allDay ? "date" : "datetime-local"}
                value={allDay ? start.slice(0, 10) : start}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label className="calendar-field">
              Ends
              <input
                required
                type={allDay ? "date" : "datetime-local"}
                value={allDay ? end.slice(0, 10) : end}
                min={allDay ? start.slice(0, 10) : start}
                onChange={(event) => setEnd(event.target.value)}
              />
            </label>
          </div>
          <div className="calendar-options">
            <label className="calendar-check">
              <input
                type="checkbox"
                checked={allDay}
                onChange={(event) => {
                  const isAllDay = event.target.checked;
                  setAllDay(isAllDay);
                  if (isAllDay) setEnd(start);
                }}
              />
              All day
            </label>
            <label className="calendar-field">
              Reminder
              <select value={reminder} onChange={(event) => setReminder(event.target.value)}>
                <option value="">No reminder</option>
                <option value="0">At event time</option>
                <option value="5">5 minutes before</option>
                <option value="10">10 minutes before</option>
                <option value="15">15 minutes before</option>
                <option value="30">30 minutes before</option>
                <option value="60">1 hour before</option>
                <option value="1440">1 day before</option>
              </select>
            </label>
          </div>
          <label className="calendar-field">
            Location
            <input
              maxLength={1024}
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Optional"
            />
          </label>
          <label className="calendar-field">
            Notes
            <textarea
              maxLength={8192}
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional"
            />
          </label>
          <p className="calendar-timezone-note">Times use {timeZone}. Only this event will be added; other job timeline entries stay in Nuse.</p>
          <div className="calendar-actions">
            <button type="button" className="quiet-button" onClick={onClose}>Cancel</button>
            <button type="submit" className="primary-button" disabled={!formReady || saving || saved}>
              {saving ? "Saving…" : "Save to Google Calendar"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
