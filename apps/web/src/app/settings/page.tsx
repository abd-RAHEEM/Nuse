"use client";

import { useEffect, useState } from "react";
import { Icon, NuseShell } from "@/components/nuse-shell";
import { ApiError, api } from "@/lib/api/client";
import type { Integration, IntegrationCalendar, IntegrationDatabase } from "@/types/api";

type Provider = "notion" | "calendar";
type ApiProvider = Integration["provider"];

export default function SettingsPage() {
  const [connection, setConnection] = useState<Provider | null>(null);
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [databases, setDatabases] = useState<IntegrationDatabase[]>([]);
  const [calendars, setCalendars] = useState<IntegrationCalendar[]>([]);
  const [selectedDestination, setSelectedDestination] = useState("");

  useEffect(() => {
    const connectedCalendar =
      new URLSearchParams(window.location.search).get("connected") === "google_calendar";
    const loadIntegrations = async () => {
      try {
        const { items } = await api.integrations.list();
        setIntegrations(items);
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
      } catch (error) {
        setMessage(error instanceof ApiError ? error.message : "Integration settings could not be loaded.");
      } finally {
        setLoaded(true);
      }
    };
    void loadIntegrations();
  }, []);

  const connectionName = connection === "notion" ? "Notion" : "Google Calendar";
  const apiProvider = (provider: Provider): ApiProvider =>
    provider === "notion" ? "notion" : "google_calendar";
  const integrationFor = (provider: Provider) =>
    integrations.find((item) => item.provider === apiProvider(provider));
  const statusFor = (provider: Provider) => integrationFor(provider)?.status ?? "disconnected";

  const openConnection = (provider: Provider) => {
    const integration = integrationFor(provider);
    const destinationKey = provider === "notion" ? "dataSourceId" : "calendarId";
    const destination = integration?.config[destinationKey];
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
        const integration = await api.integrations.connectNotion(token);
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
      } else {
        const { authUrl } = await api.integrations.startGoogleCalendar();
        window.location.assign(authUrl);
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The connection could not be completed.");
    } finally {
      setSaving(false);
    }
  };

  const saveDestination = async () => {
    if (!connection || !selectedDestination) return;
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
    const name = provider === "notion" ? "Notion" : "Google Calendar";
    if (!window.confirm(`Disconnect ${name}? Nuse will remove its saved access; nothing will be deleted from ${name}.`)) {
      return;
    }
    try {
      await api.integrations.disconnect(apiProvider(provider));
      setIntegrations((items) => items.filter((item) => item.provider !== apiProvider(provider)));
      if (provider === "notion") setDatabases([]);
      else setCalendars([]);
      setMessage(`${name} disconnected. Nothing was deleted from the external service.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : `${name} could not be disconnected.`);
    }
  };

  const destinationReady = connection === "notion"
    ? databases.length > 0
    : calendars.length > 0;
  const alreadyConnected = connection !== null && statusFor(connection) === "connected";

  return (
    <NuseShell title="Settings" eyebrow="Keep Nuse yours">
      <div className="settings-stack">
        <section className="settings-panel">
          <div className="settings-heading">
            <div><p className="eyebrow">Profile</p><h2>Your desk</h2></div>
            <button className="quiet-button" disabled>Edit profile</button>
          </div>
          <div className="profile-large">
            <span className="avatar large">AR</span>
            <span><strong>Abdul Raheem</strong><small>Asia/Kolkata · Personal workspace</small></span>
          </div>
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
            detail="Add scheduled job events to a Google calendar"
            loading={!loaded}
            onOpen={() => openConnection("calendar")}
            onDisconnect={() => void disconnect("calendar")}
          />
          {message && !connection && <p className="capture-fallback" role="status">{message}</p>}
        </section>

        <section className="settings-panel">
          <div className="settings-heading">
            <div><p className="eyebrow">Account</p><h2>Security and data</h2></div>
          </div>
          <button className="settings-action" disabled>
            <span><strong>Change PIN</strong><small>Update the six-digit key for this desk</small></span>
            <Icon name="arrow" size={16} />
          </button>
          <button className="settings-action" disabled>
            <span><strong>Export your data</strong><small>Download jobs, events, and resources as JSON or CSV</small></span>
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
            <span className={`integration-mark ${connection === "notion" ? "notion" : "calendar"}`}>
              {connection === "notion" ? "N" : "31"}
            </span>
            <p className="eyebrow">{alreadyConnected ? "Integration settings" : "Connect integration"}</p>
            <h2 id="connect-title">{alreadyConnected ? `Choose a ${connection === "notion" ? "database" : "calendar"}.` : `Bring ${connectionName} into your desk.`}</h2>
            <p className="modal-copy">
              {connection === "notion"
                ? "Connect a Notion personal integration, then choose a database shared with it."
                : "Authorize Nuse with Google, then choose where scheduled job events should go."}
            </p>
            {connection === "notion" && !alreadyConnected && (
              <label className="modal-field">Integration token
                <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Paste your Notion token" autoComplete="off" />
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
            {message && <p className="capture-fallback" role="alert">{message}</p>}
            {alreadyConnected && destinationReady ? (
              <button className="primary-button wide" onClick={() => void saveDestination()} disabled={saving || !selectedDestination}>
                {saving ? "Saving…" : "Save destination"} <Icon name="arrow" size={16} />
              </button>
            ) : alreadyConnected ? (
              <p className="page-support">{loaded ? "Loading available destinations…" : "Loading integration details…"}</p>
            ) : (
              <button className="primary-button wide" onClick={() => void connect()} disabled={saving || !loaded || (connection === "notion" && !token.trim())}>
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
  const name = notion ? "Notion" : "Google Calendar";
  const connected = status === "connected";
  return (
    <div className="integration-row">
      <span className={`integration-mark ${notion ? "notion" : "calendar"}`}>{notion ? "N" : "31"}</span>
      <span><strong>{name}</strong><small>{detail}</small></span>
      <span className="connection-status">{loading ? "Loading" : status.replaceAll("_", " ")}</span>
      <button className="quiet-button" onClick={onOpen} disabled={loading}>
        {connected ? "Change destination" : "Connect"} <Icon name="arrow" size={14} />
      </button>
      {connected && <button className="text-button" onClick={onDisconnect}>Disconnect</button>}
    </div>
  );
}
