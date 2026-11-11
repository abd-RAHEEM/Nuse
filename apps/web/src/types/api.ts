export type JobStatus =
  | "saved"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "on_hold";

export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "internship"
  | "freelance"
  | "other";

export type WorkMode = "onsite" | "hybrid" | "remote";

export type ResourceCategory =
  | "ai_tool"
  | "course"
  | "certification"
  | "research"
  | "article"
  | "developer_resource"
  | "other";

export type VerificationStatus = "unverified" | "verified" | "unverifiable";

export type Provenance = "extracted" | "suggested" | "user_edited" | "not_found";

export type Field<T> = {
  value: T | null;
  provenance: Provenance;
  source?: string;
};

export type FieldProvenance = Record<
  string,
  { provenance: Provenance; source?: string }
>;

export type TagRef = { id: string; name: string };

export type Page<T> = { items: T[]; nextCursor: string | null };

export type Integration = {
  id: string;
  provider: "notion" | "google_calendar" | "gmail";
  status: string;
  accountLabel: string | null;
  config: Record<string, unknown>;
  scopes: string[];
  lastUsedAt: string | null;
  lastError: string | null;
};

export type IntegrationDatabase = { id: string; title: string };
export type IntegrationCalendar = { id: string; name: string; primary: boolean };
export type GmailSyncRun = {
  id: string;
  status: "running" | "completed" | "failed";
  mode: "initial" | "incremental";
  messagesScanned: number;
  jobsMatched: number;
  jobsUpdated: number;
  reviewQueued: number;
  unmatchedDiscarded: number;
  lastError: string | null;
  createdAt: string;
  finishedAt: string | null;
};
export type GmailReviewItem = {
  messageId: string;
  jobId: string;
  company: string;
  title: string;
  sender: string | null;
  subject: string;
  receivedAt: string;
  suggestedStatus: JobStatus | null;
};

export type JobSummary = {
  id: string;
  company: string;
  title: string;
  location: string | null;
  employmentType: EmploymentType | null;
  workMode: WorkMode | null;
  status: JobStatus;
  appliedOn: string | null;
  nextFollowUpOn: string | null;
  deadline: string | null;
  tags: TagRef[];
  sourceUrl: string | null;
  archived: boolean;
  createdAt: string;
  updatedAt: string;
};

export type Application = {
  id: string;
  status: JobStatus;
  appliedOn: string | null;
  nextFollowUpOn: string | null;
  notes: string | null;
};

export type JobEvent = {
  id: string;
  jobId: string;
  type: string;
  title: string;
  notes: string | null;
  occurredAt: string;
  scheduledFor: string | null;
  allDay: boolean;
  system: boolean;
  calendarLinked: boolean;
  createdAt: string;
};

export type JobDetail = JobSummary & {
  externalJobId: string | null;
  description: string | null;
  requirements: string | null;
  notes: string | null;
  application: Application | null;
  timeline: JobEvent[];
  fieldProvenance: FieldProvenance;
  extractionId: string | null;
};

export type ResourceSummary = {
  id: string;
  title: string;
  category: ResourceCategory;
  sourceUrl: string | null;
  sourcePlatform: string | null;
  description: string | null;
  tags: TagRef[];
  isFavorite: boolean;
  isSavedForLater: boolean;
  collectionIds: string[];
  verificationStatus: VerificationStatus;
  createdAt: string;
};

export type ResourceDetail = ResourceSummary & {
  summary: string | null;
  notes: string | null;
  details: Record<string, unknown> | null;
  verificationNote: string | null;
  fieldProvenance: FieldProvenance;
  extractionId: string | null;
  updatedAt: string;
};

export type DashboardResponse = {
  user: { displayName: string | null; username: string };
  counts: {
    applicationsTracked: number;
    interviewsActive: number;
    resourcesTotal: number;
  };

  upcoming: {
    kind: "follow_up" | "deadline" | "interview" | "assessment";
    at: string;
    allDay: boolean;
    overdue: boolean;
    job: { id: string; company: string; title: string };
    eventId: string | null;
  }[];
  recentActivity: (JobEvent & {
    job: { id: string; company: string; title: string };
  })[];
  recentResources: ResourceSummary[];
};

export type Extraction = {
  id: string;
  type: "job" | "resource";
  status: string;
  input: { url: string | null; normalizedUrl: string | null; hasText: boolean };
  detectedSource: { kind: string; domain: string | null };
  detectedType: "job" | "resource" | "unknown";
  steps: { key: string; state: string }[];
  result: Record<string, { value: unknown; provenance: Provenance; source?: string }> | null;
  error: { code: string; message: string; hint: string } | null;
  duplicateOf: { kind: string; id: string; title: string } | null;
  createdAt: string;
  finishedAt: string | null;
};
