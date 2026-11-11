"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Icon, NuseShell } from "@/components/nuse-shell";
import { ApiError, api } from "@/lib/api/client";
import type { Integration, IntegrationCalendar, IntegrationDatabase } from "@/types/api";

type Provider = "notion" | "calendar" | "gmail";
type ApiProvider = Integration["provider"];

export default function SettingsPage() {
  const router = useRouter();
  const [connection, setConnection] = useState<Provider | null>(null);
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [databases, setDatabases] = useState<IntegrationDatabase[]>([]);
  const [calendars, setCalendars] = useState<IntegrationCalendar[]>([]);
  const [selectedDestination, setSelectedDestination] = useState("");
  const [profileName, setProfileName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState("");
  const [pinFormOpen, setPinFormOpen] = useState(false);
  const [currentPin, setCurrentPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [pinSaving, setPinSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const profileInitials = profileName.trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase() || "N";

  useEffect(() => {
    const connectedCalendar =
      new URLSearchParams(window.location.search).get("connected") === "google_calendar";
    const connectedGmail =
      new URLSearchParams(window.location.search).get("connected") === "gmail";
    const gmailCancelled =
      new URLSearchParams(window.location.search).get("gmail") === "cancelled";
    const loadIntegrations = async () => {
      try {
        const { items } = await api.integrations.list();
        const profile = await api.settings.get();
        setIntegrations(items);
        setProfileName(profile.displayName ?? "");
        setTimezone(profile.timezone);
        const notion = items.find((item) => item.provider === "notion");
        if (notion?.status === "connected") {
          setSelectedDestination(
            typeof notion.config.dataSourceId === "string" ? notion.config.dataSourceId : "",
          );
          setDatabases((await api.integrations.notionDatabases()).items);
        }
        const calendar = items.find((item) => item.provider === "google_calendar");
        if (calendar?.status === "connected") {
          setSelectedDestination(
            typeof calendar.config.calendarId === "string" ? calendar.config.calendarId : "",
          );
          setCalendars((await api.integrations.calendars()).items);
        }
        if (connectedCalendar) {
          setConnection("calendar");
          window.history.replaceState(null, "", "/settings");
        }
        if (connectedGmail) {
          setConnection("gmail");
          window.history.replaceState(null, "", "/settings");
        }
        if (gmailCancelled) {
          setMessage("Gmail was not connected. You can try again when ready.");
          window.history.replaceState(null, "", "/settings");
        }
      } catch (error) {
        setMessage(error instanceof ApiError ? error.message : "Integration settings could not be loaded.");
      } finally {
        setLoaded(true);
      }
    };
    void loadIntegrations();
  }, []);

  const connectionName =
    connection === "notion" ? "Notion" : connection === "gmail" ? "Gmail" : "Google Calendar";
  const apiProvider = (provider: Provider): ApiProvider =>
    provider === "calendar" ? "google_calendar" : provider;
  const integrationFor = (provider: Provider) =>
    integrations.find((item) => item.provider === apiProvider(provider));
  const statusFor = (provider: Provider) => integrationFor(provider)?.status ?? "disconnected";

  const openConnection = (provider: Provider) => {
    const integration = integrationFor(provider);
    const destinationKey =
      provider === "notion" ? "dataSourceId" : provider === "calendar" ? "calendarId" : null;
    const destination = destinationKey ? integration?.config[destinationKey] : null;
    setSelectedDestination(typeof destination === "string" ? destination : "");
    setMessage("");
    setConnection(provider);
  };

  const connect = async () => {
    if (!connection) return;
    setSaving(true);
    setMessage("");
    try {
      if (connection === "notion") {
        const integration = await api.integrations.connectNotion(token.trim() || undefined);
        setIntegrations((items) => [
          ...items.filter((item) => item.provider !== integration.provider),
          integration,
        ]);
        setToken("");
        const result = await api.integrations.notionDatabases();
        setDatabases(result.items);
        if (result.items.length === 0) {
          setMessage("No shared Notion databases were found. Share a database with your integration, then try again.");
        }
      } else if (connection === "calendar") {
        const { authUrl } = await api.integrations.startGoogleCalendar();
        window.location.assign(authUrl);
      } else {
        const { authUrl } = await api.integrations.startGmailOAuth();
        window.location.assign(authUrl);
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The connection could not be completed.");
    } finally {
      setSaving(false);
    }
  };

  const refreshDestinations = async () => {
    if (!connection) return;
    setSaving(true);
    setMessage("");
    try {
      if (connection === "notion") {
        const result = await api.integrations.notionDatabases();
        setDatabases(result.items);
        if (result.items.length === 0) {
          setMessage("No shared Notion databases were found. Share one with the integration, then try again.");
        }
      } else if (connection === "calendar") {
        const result = await api.integrations.calendars();
        setCalendars(result.items);
        if (result.items.length === 0) {
          setMessage("No calendars are available for this Google account.");
        }
      } else {
        setMessage("Gmail does not need a destination to sync.");
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Available destinations could not be loaded.");
    } finally {
      setSaving(false);
    }
  };

  const saveDestination = async () => {
    if (!connection || connection === "gmail" || !selectedDestination) return;
    setSaving(true);
    setMessage("");
    try {
      const integration = connection === "notion"
        ? await api.integrations.configureNotion(selectedDestination)
        : await api.integrations.configureCalendar(selectedDestination);
      setIntegrations((items) => [
        ...items.filter((item) => item.provider !== integration.provider),
        integration,
      ]);
      setConnection(null);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The destination could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const disconnect = async (provider: Provider) => {
    const name =
      provider === "notion" ? "Notion" : provider === "gmail" ? "Gmail" : "Google Calendar";
    if (!window.confirm(`Disconnect ${name}? Nuse will remove its saved access; nothing will be deleted from ${name}.`)) {
      return;
    }
    try {
      await api.integrations.disconnect(apiProvider(provider));
      setIntegrations((items) => items.filter((item) => item.provider !== apiProvider(provider)));
      if (provider === "notion") setDatabases([]);
      else if (provider === "calendar") setCalendars([]);
      setMessage(`${name} disconnected. Nothing was deleted from the external service.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : `${name} could not be disconnected.`);
    }
  };

  const destinationReady = connection === "notion"
    ? databases.length > 0
    : connection === "calendar" ? calendars.length > 0 : true;
  const alreadyConnected = connection !== null && statusFor(connection) === "connected";
  const gmailConnection = integrationFor("gmail");
  const gmailLastSync = gmailConnection?.config.lastSyncAt;
  const gmailLastSyncAt =
    typeof gmailLastSync === "string"
      ? new Date(gmailLastSync).toLocaleString("en-IN")
      : null;

  const saveProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProfileSaving(true);
    setProfileMessage("");
    try {
      const profile = await api.settings.update({
        displayName: profileName.trim() || null,
        timezone,
      });
      setProfileName(profile.displayName ?? "");
      setTimezone(profile.timezone);
      setProfileMessage("Profile saved.");
      window.location.reload();
    } catch (error) {
      setProfileMessage(error instanceof ApiError ? error.message : "Profile settings could not be saved.");
    } finally {
      setProfileSaving(false);
    }
  };

  const changePin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");
    if (newPin !== confirmPin) {
      setMessage("The new PIN entries do not match.");
      return;
    }
    setPinSaving(true);
    try {
      await api.auth.changePin(currentPin, newPin);
      setMessage("PIN changed. Sign in again with your new PIN.");
      window.setTimeout(() => router.replace("/login"), 900);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The PIN could not be changed.");
    } finally {
      setPinSaving(false);
    }
  };

  const downloadExport = async (kind: "jobs" | "resources", format: "csv" | "json") => {
    setExporting(true);
    setMessage("");
    try {
      if (kind === "jobs") await api.exports.jobs(format, true);
      else await api.exports.resources(format);
      setMessage(`${kind === "jobs" ? "Jobs" : "Resources"} exported as ${format.toUpperCase()}.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The export could not be created.");
    } finally {
      setExporting(false);
    }
  };

  const signOut = async () => {
    try {
      await api.auth.logout();
      router.replace("/login");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "You could not be signed out.");
    }
  };

  return (
    <NuseShell title="Settings" eyebrow="Keep Nuse yours">
      <div className="settings-stack">
        <section className="settings-panel">
          <div className="settings-heading">
            <div><p className="eyebrow">Profile</p><h2>Your desk</h2></div>
          </div>
          <div className="profile-large">
            <span className="avatar large">{profileInitials}</span>
            <span><strong>{profileName || "Your desk"}</strong><small>{timezone} · Personal workspace</small></span>
          </div>
          <form className="settings-profile-form" onSubmit={saveProfile}>
            <label>Display name<input value={profileName} onChange={(event) => setProfileName(event.target.value)} maxLength={120} /></label>
            <label>Timezone<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Kolkata" required /></label>
            <button className="secondary-button" type="submit" disabled={profileSaving || !loaded}>{profileSaving ? "Saving…" : "Save profile"}</button>
            {profileMessage && <p className="page-support" role="status">{profileMessage}</p>}
          </form>
        </section>

        <section className="settings-panel">
          <div className="settings-heading">
            <div><p className="eyebrow">Connections</p><h2>Integrations</h2></div>
          </div>
          <IntegrationRow
            provider="notion"
            status={statusFor("notion")}
            detail="Send resources to a database you choose"
            loading={!loaded}
            onOpen={() => openConnection("notion")}
            onDisconnect={() => void disconnect("notion")}
          />
          <IntegrationRow
            provider="calendar"
            status={statusFor("calendar")}
            detail="Send only events you choose to Google Calendar"
            loading={!loaded}
            onOpen={() => openConnection("calendar")}
            onDisconnect={() => void disconnect("calendar")}
          />
          <IntegrationRow
            provider="gmail"
            status={statusFor("gmail")}
            detail="Read-only email updates; unmatched messages are discarded"
            loading={!loaded}
            onOpen={() => openConnection("gmail")}
            onDisconnect={() => void disconnect("gmail")}
          />
          {message && !connection && <p className="capture-fallback" role="status">{message}</p>}
        </section>

        <section className="settings-panel">
          <div className="settings-heading">
            <div><p className="eyebrow">Account</p><h2>Security and data</h2></div>
          </div>
          <button className="settings-action" onClick={() => setPinFormOpen((open) => !open)} aria-expanded={pinFormOpen}>
            <span><strong>Change PIN</strong><small>Update the six-digit key for this desk</small></span>
            <Icon name="arrow" size={16} />
          </button>
          {pinFormOpen && <form className="settings-profile-form pin-change-form" onSubmit={changePin}>
            <label>Current PIN<input type="password" inputMode="numeric" autoComplete="current-password" maxLength={6} value={currentPin} onChange={(event) => setCurrentPin(event.target.value.replace(/\D/g, "").slice(0, 6))} required /></label>
            <label>New PIN<input type="password" inputMode="numeric" autoComplete="new-password" maxLength={6} value={newPin} onChange={(event) => setNewPin(event.target.value.replace(/\D/g, "").slice(0, 6))} required /></label>
            <label>Confirm new PIN<input type="password" inputMode="numeric" autoComplete="new-password" maxLength={6} value={confirmPin} onChange={(event) => setConfirmPin(event.target.value.replace(/\D/g, "").slice(0, 6))} required /></label>
            <button className="secondary-button" type="submit" disabled={pinSaving || newPin.length !== 6 || currentPin.length !== 6}>{pinSaving ? "Changing PIN…" : "Change PIN"}</button>
          </form>}
          <div className="settings-export">
            <span><strong>Export your data</strong><small>Download jobs, events, and resources</small></span>
            <div className="settings-export-actions">
              <button className="quiet-button" onClick={() => void downloadExport("jobs", "csv")} disabled={exporting}>Jobs CSV</button>
              <button className="quiet-button" onClick={() => void downloadExport("jobs", "json")} disabled={exporting}>Jobs JSON</button>
              <button className="quiet-button" onClick={() => void downloadExport("resources", "csv")} disabled={exporting}>Resources CSV</button>
              <button className="quiet-button" onClick={() => void downloadExport("resources", "json")} disabled={exporting}>Resources JSON</button>
            </div>
          </div>
          <button className="settings-action" onClick={() => void signOut()}>
            <span><strong>Sign out</strong><small>End this session on this browser</small></span>
            <Icon name="arrow" size={16} />
          </button>
        </section>
      </div>

      {connection && (
        <div className="modal-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setConnection(null);
        }}>
          <section className="connect-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title">
            <button className="icon-button modal-close" onClick={() => setConnection(null)} aria-label="Close connection dialog">×</button>
            <span className={`integration-mark ${connection}`}>
              {connection === "notion" ? "N" : connection === "calendar" ? "31" : "G"}
            </span>
            <p className="eyebrow">{alreadyConnected ? "Integration settings" : "Connect integration"}</p>
            <h2 id="connect-title">
              {alreadyConnected
                ? connection === "gmail"
                  ? "Gmail is connected."
                  : `Choose a ${connection === "notion" ? "database" : "calendar"}.`
                : `Bring ${connectionName} into your desk.`}
            </h2>
            <p className="modal-copy">
              {connection === "notion"
                ? "Connect a Notion personal integration, then choose a database shared with it."
                : connection === "calendar"
                  ? "Authorize Nuse with Google, then choose where events you explicitly add should go. Nuse never syncs a whole job timeline."
                  : "Nuse requests read-only Gmail access. The first sync checks 90 days; later syncs check new mail. A local rules-based classifier processes likely application emails on your Nuse server. Only matched message metadata is retained; unmatched mail, bodies, and attachments are not saved."}
            </p>
            {connection === "notion" && !alreadyConnected && (
              <label className="modal-field">Integration token
                <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Paste a token, or leave blank to use the server setting" autoComplete="off" />
              </label>
            )}
            {connection === "notion" && alreadyConnected && (
              <label className="modal-field">Destination database
                <select value={selectedDestination} onChange={(event) => setSelectedDestination(event.target.value)}>
                  <option value="">Choose a database</option>
                  {databases.map((database) => <option key={database.id} value={database.id}>{database.title || "Untitled database"}</option>)}
                </select>
              </label>
            )}
            {connection === "calendar" && alreadyConnected && (
              <label className="modal-field">Destination calendar
                <select value={selectedDestination} onChange={(event) => setSelectedDestination(event.target.value)}>
                  <option value="">Choose a calendar</option>
                  {calendars.map((calendar) => <option key={calendar.id} value={calendar.id}>{calendar.name}{calendar.primary ? " (primary)" : ""}</option>)}
                </select>
              </label>
            )}
            {connection === "gmail" && alreadyConnected && (
              <p className="page-support gmail-connection-detail">
                {gmailConnection?.accountLabel ?? "Google account"}
                {gmailLastSyncAt ? ` · Last synced ${gmailLastSyncAt}` : " · No sync has run yet"}
              </p>
            )}
            {message && <p className="capture-fallback" role="alert">{message}</p>}
            {alreadyConnected && connection === "gmail" ? (
              <button className="primary-button wide" onClick={() => router.push("/jobs")}>
                Review job updates <Icon name="arrow" size={16} />
              </button>
            ) : alreadyConnected && destinationReady ? (
              <button className="primary-button wide" onClick={() => void saveDestination()} disabled={saving || !selectedDestination}>
                {saving ? "Saving…" : "Save destination"} <Icon name="arrow" size={16} />
              </button>
            ) : alreadyConnected ? (
              <div className="destination-empty">
                <p className="page-support">
                  {saving
                    ? "Loading available destinations…"
                    : connection === "notion"
                      ? "No shared Notion databases were found. Share one with the integration, then try again."
                      : "No calendars are available for this Google account."}
                </p>
                <button className="quiet-button" onClick={() => void refreshDestinations()} disabled={saving}>
                  {saving ? "Checking…" : "Try again"}
                </button>
              </div>
            ) : (
              <button className="primary-button wide" onClick={() => void connect()} disabled={saving || !loaded}>
                {saving ? "Connecting…" : "Continue"} <Icon name="arrow" size={16} />
              </button>
            )}
            <button className="quiet-button modal-cancel" onClick={() => setConnection(null)}>Not now</button>
          </section>
        </div>
      )}
    </NuseShell>
  );
}

function IntegrationRow({
  provider,
  status,
  detail,
  loading,
  onOpen,
  onDisconnect,
}: {
  provider: Provider;
  status: string;
  detail: string;
  loading: boolean;
  onOpen: () => void;
  onDisconnect: () => void;
}) {
  const notion = provider === "notion";
  const gmail = provider === "gmail";
  const name = notion ? "Notion" : gmail ? "Gmail" : "Google Calendar";
  const connected = status === "connected";
  return (
    <div className="integration-row">
      <span className={`integration-mark ${provider}`}>{notion ? "N" : gmail ? "G" : "31"}</span>
      <span><strong>{name}</strong><small>{detail}</small></span>
      <span className="connection-status">{loading ? "Loading" : status.replaceAll("_", " ")}</span>
      <button className="quiet-button" onClick={onOpen} disabled={loading}>
        {connected ? gmail ? "Manage" : "Change destination" : "Connect"} <Icon name="arrow" size={14} />
      </button>
      {connected && <button className="text-button" onClick={onDisconnect}>Disconnect</button>}
    </div>
  );
}
