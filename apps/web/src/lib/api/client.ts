import type {
  DashboardResponse,
  JobDetail,
  JobSummary,
  Page,
  ResourceDetail,
  ResourceSummary,
  Extraction,
  Integration,
  IntegrationCalendar,
  IntegrationDatabase,
  GmailReviewItem,
  GmailSyncRun,
  JobStatus,
} from "@/types/api";

export type ApiMode = "mock" | "live";

export type ApiUser = {
  id: string;
  username: string;
  displayName: string | null;
  createdAt: string;
};

type AuthResponse = { user: ApiUser };

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const apiMode: ApiMode =
  process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-Requested-With", "hub");
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code: string | null = null;
    try {
      const problem = (await response.json()) as {
        detail?: string;
        title?: string;
        code?: string;
      };
      message = problem.detail ?? problem.title ?? message;
      code = problem.code ?? null;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { Accept: "application/json, text/csv" },
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let code: string | null = null;
    try {
      const problem = (await response.json()) as {
        detail?: string;
        title?: string;
        code?: string;
      };
      message = problem.detail ?? problem.title ?? message;
      code = problem.code ?? null;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new ApiError(message, response.status, code);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});

export const api = {
  auth: {
    async login(username: string, pin: string): Promise<ApiUser> {
      const result = await request<AuthResponse>("/auth/login", json({ username, pin }));
      return result.user;
    },
    async signup(username: string, pin: string, displayName?: string): Promise<ApiUser> {
      const result = await request<AuthResponse>(
        "/auth/signup",
        json({ username, pin, displayName }),
      );
      return result.user;
    },
    async me(): Promise<ApiUser> {
      return request<ApiUser>("/auth/me");
    },
    async changePin(currentPin: string, newPin: string): Promise<void> {
      await request<void>(
        "/auth/change-pin",
        json({ currentPin, newPin }),
      );
    },
    async logout(): Promise<void> {
      await request<void>("/auth/logout", json({}));
    },
  },
  dashboard: {
    get(): Promise<DashboardResponse> {
      return request<DashboardResponse>("/dashboard");
    },
  },
  settings: {
    get(): Promise<{ displayName: string | null; timezone: string }> {
      return request<{ displayName: string | null; timezone: string }>("/settings");
    },
    update(input: {
      displayName?: string | null;
      timezone?: string;
    }): Promise<{ displayName: string | null; timezone: string }> {
      return request<{ displayName: string | null; timezone: string }>(
        "/settings",
        { method: "PATCH", body: JSON.stringify(input) },
      );
    },
  },
  exports: {
    jobs(format: "csv" | "json", includeArchived = false): Promise<void> {
      const query = new URLSearchParams({
        format,
        includeArchived: String(includeArchived),
      });
      return downloadFile(
        `/exports/jobs?${query.toString()}`,
        `nuse-jobs.${format}`,
      );
    },
    resources(format: "csv" | "json"): Promise<void> {
      return downloadFile(
        `/exports/resources?format=${format}`,
        `nuse-resources.${format}`,
      );
    },
  },
  jobs: {
    list(params: {
      q?: string;
      status?: string[];
      company?: string;
      location?: string;
      tags?: string[];
      appliedFrom?: string;
      appliedTo?: string;
      followUpBefore?: string;
      archived?: boolean;
      sort?: "newest" | "oldest" | "next_action";
      cursor?: string;
      limit?: number;
    } = {}): Promise<Page<JobSummary>> {
      const query = new URLSearchParams();
      if (params.q) query.set("q", params.q);
      for (const value of params.status ?? []) query.append("status[]", value);
      if (params.company) query.set("company", params.company);
      if (params.location) query.set("location", params.location);
      for (const value of params.tags ?? []) query.append("tag[]", value);
      if (params.appliedFrom) query.set("appliedFrom", params.appliedFrom);
      if (params.appliedTo) query.set("appliedTo", params.appliedTo);
      if (params.followUpBefore) query.set("followUpBefore", params.followUpBefore);
      if (params.archived !== undefined) query.set("archived", String(params.archived));
      if (params.sort) query.set("sort", params.sort);
      if (params.cursor) query.set("cursor", params.cursor);
      if (params.limit) query.set("limit", String(params.limit));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<Page<JobSummary>>(`/jobs${suffix}`);
    },
    get(id: string): Promise<JobDetail> {
      return request<JobDetail>(`/jobs/${id}`);
    },
    create(input: {
      intent: "saved" | "applied";
      company: string;
      title: string;
      location?: string;
      sourceUrl?: string;
      employmentType?: string;
      workMode?: string;
      description?: string;
      extractionId?: string;
    }): Promise<JobDetail> {
      return request<JobDetail>("/jobs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(input),
      });
    },
    update(id: string, input: {
      status?: string;
      archived?: boolean;
      notes?: string;
      location?: string;
      title?: string;
      company?: string;
    }): Promise<JobDetail> {
      return request<JobDetail>(`/jobs/${id}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      });
    },
    remove(id: string): Promise<void> {
      return request<void>(`/jobs/${id}`, { method: "DELETE" });
    },
    createEvent(id: string, input: {
      type: "assessment" | "interview" | "follow_up" | "note";
      title: string;
      notes?: string;
      scheduledFor?: string;
      allDay?: boolean;
    }): Promise<JobDetail["timeline"][number]> {
      return request<JobDetail["timeline"][number]>(`/jobs/${id}/events`, {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    updateEvent(
      jobId: string,
      eventId: string,
      input: {
        title?: string;
        notes?: string | null;
        scheduledFor?: string;
        allDay?: boolean;
      },
    ): Promise<JobDetail["timeline"][number]> {
      return request<JobDetail["timeline"][number]>(
        `/jobs/${jobId}/events/${eventId}`,
        { method: "PATCH", body: JSON.stringify(input) },
      );
    },
  },
  resources: {
    get(id: string): Promise<ResourceDetail> {
      return request<ResourceDetail>(`/resources/${id}`);
    },
    list(params: { q?: string; category?: string } = {}): Promise<Page<ResourceSummary>> {
      const query = new URLSearchParams();
      if (params.q) query.set("q", params.q);
      if (params.category) query.set("category", params.category);
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<Page<ResourceSummary>>(`/resources${suffix}`);
    },
    create(input: {
      title: string;
      category: ResourceSummary["category"];
      sourceUrl?: string;
      sourcePlatform?: string;
      description?: string;
      extractionId?: string;
    }): Promise<ResourceSummary> {
      return request<ResourceSummary>("/resources", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(input),
      });
    },
    update(id: string, input: {
      isFavorite?: boolean;
      notes?: string;
      description?: string;
    }): Promise<ResourceDetail> {
      return request<ResourceDetail>(`/resources/${id}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      });
    },
    remove(id: string): Promise<void> {
      return request<void>(`/resources/${id}`, { method: "DELETE" });
    },
  },
  extractions: {
    create(input: { type: "job" | "resource"; url?: string; text?: string }): Promise<Extraction> {
      return request<Extraction>("/extractions", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(input),
      });
    },
    get(id: string): Promise<Extraction> {
      return request<Extraction>(`/extractions/${id}`);
    },
    remove(id: string): Promise<void> {
      return request<void>(`/extractions/${id}`, { method: "DELETE" });
    },
  },
  integrations: {
    list(): Promise<{ items: Integration[] }> {
      return request<{ items: Integration[] }>("/integrations");
    },
    connectNotion(token?: string): Promise<Integration> {
      return request<Integration>("/integrations/notion/connect", {
        method: "POST",
        body: JSON.stringify(token ? { token } : {}),
      });
    },
    notionDatabases(query?: string): Promise<{ items: IntegrationDatabase[] }> {
      const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
      return request<{ items: IntegrationDatabase[] }>(
        `/integrations/notion/databases${suffix}`,
      );
    },
    configureNotion(dataSourceId: string): Promise<Integration> {
      return request<Integration>("/integrations/notion/config", {
        method: "PUT",
        body: JSON.stringify({ dataSourceId }),
      });
    },
    startGoogleCalendar(): Promise<{ authUrl: string }> {
      return request<{ authUrl: string }>(
        "/integrations/google-calendar/oauth/start",
      );
    },
    startGmailOAuth(): Promise<{ authUrl: string }> {
      return request<{ authUrl: string }>(
        "/integrations/gmail/oauth/start",
        json({}),
      );
    },
    startGmailSync(): Promise<GmailSyncRun> {
      return request<GmailSyncRun>("/integrations/gmail/sync", json({}));
    },
    advanceGmailSync(runId: string): Promise<GmailSyncRun> {
      return request<GmailSyncRun>(
        `/integrations/gmail/sync/${encodeURIComponent(runId)}/step`,
        json({}),
      );
    },
    gmailReviews(): Promise<{ items: GmailReviewItem[] }> {
      return request<{ items: GmailReviewItem[] }>("/integrations/gmail/review");
    },
    resolveGmailReview(
      messageId: string,
      status: JobStatus | "ignore",
    ): Promise<{ status: "processed" | "ignored"; jobId: string }> {
      return request(
        `/integrations/gmail/review/${encodeURIComponent(messageId)}`,
        json({ status }),
      );
    },
    calendars(): Promise<{ items: IntegrationCalendar[] }> {
      return request<{ items: IntegrationCalendar[] }>(
        "/integrations/google-calendar/calendars",
      );
    },
    configureCalendar(calendarId: string): Promise<Integration> {
      return request<Integration>("/integrations/google-calendar/config", {
        method: "PUT",
        body: JSON.stringify({ calendarId }),
      });
    },
    exportToNotion(resourceIds: string[]): Promise<{
      results: {
        resourceId: string;
        status: "created" | "updated" | "failed";
        notionUrl: string | null;
        error: string | null;
      }[];
    }> {
      return request("/integrations/notion/export", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ resourceIds }),
      });
    },
    createCalendarEvent(input: {
      jobId?: string;
      jobEventId?: string;
      title?: string;
      description?: string;
      location?: string;
      startsAt: string;
      endsAt?: string;
      allDay?: boolean;
      timeZone: string;
      reminders?: { method: "popup"; minutes: number }[];
    }): Promise<{ calendarEventId: string; htmlLink: string | null }> {
      return request("/integrations/google-calendar/events", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(input),
      });
    },
    disconnect(provider: "notion" | "google_calendar" | "gmail"): Promise<void> {
      return request<void>(`/integrations/${provider}`, { method: "DELETE" });
    },
  },
};
