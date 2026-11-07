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
    async signup(username: string, pin: string): Promise<ApiUser> {
      const result = await request<AuthResponse>("/auth/signup", json({ username, pin }));
      return result.user;
    },
    async me(): Promise<ApiUser> {
      return request<ApiUser>("/auth/me");
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
  jobs: {
    list(params: { q?: string; archived?: boolean } = {}): Promise<Page<JobSummary>> {
      const query = new URLSearchParams();
      if (params.q) query.set("q", params.q);
      if (params.archived) query.set("archived", "true");
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
    connectNotion(token: string): Promise<Integration> {
      return request<Integration>("/integrations/notion/connect", {
        method: "POST",
        body: JSON.stringify({ token }),
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
      jobId: string;
      jobEventId: string;
      title?: string;
      startsAt: string;
      endsAt?: string;
      allDay?: boolean;
      timeZone: string;
    }): Promise<{ calendarEventId: string; htmlLink: string | null }> {
      return request("/integrations/google-calendar/events", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(input),
      });
    },
    disconnect(provider: "notion" | "google_calendar"): Promise<void> {
      return request<void>(`/integrations/${provider}`, { method: "DELETE" });
    },
  },
};
