"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { NuseShell, Icon } from "@/components/nuse-shell";
import { api, apiMode } from "@/lib/api/client";
import type { ResourceDetail } from "@/types/api";

export default function ResourceDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const [resource, setResource] = useState<ResourceDetail | null>(null);
  const [error, setError] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  useEffect(() => {
    if (apiMode !== "live") return;
    api.resources.get(id).then((loaded) => {
      setResource(loaded);
      setDescription(loaded.description ?? "");
      setNotes(loaded.notes ?? "");
    }).catch(() => setError("This resource could not be found."));
  }, [id]);

  const saveDetails = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!resource) return;
    setSaving(true);
    try {
      const updated = await api.resources.update(resource.id, { description, notes });
      setResource({ ...resource, ...updated });
    } catch {
      setError("The resource details could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const deleteResource = async () => {
    if (!resource || !window.confirm("Delete this resource permanently?")) return;
    setActionBusy(true);
    try {
      await api.resources.remove(resource.id);
      router.push("/resources");
    } catch {
      setError("The resource could not be deleted.");
      setActionBusy(false);
    }
  };

  if (apiMode !== "live") {
    return <NuseShell title="Resource detail" eyebrow="Mock mode"><div className="detail-empty"><p className="eyebrow">Mock mode</p><h2>Open a live resource from the library.</h2><Link href="/resources" className="primary-button">Back to resources <Icon name="arrow" size={14} /></Link></div></NuseShell>;
  }
  return <NuseShell title={resource?.title ?? "Resource detail"} eyebrow={resource ? formatCategory(resource.category) : "Live record"}><div className="detail-page">
    <Link href="/resources" className="text-button"><Icon name="arrow" size={13} /> Back to resources</Link>
    {error && <p className="auth-error" role="alert">{error}</p>}
    {resource && <><div className="detail-hero"><span className="resource-glyph">◫</span><div><p className="eyebrow">{formatCategory(resource.category)}</p><h2>{resource.title}</h2><p>{resource.sourcePlatform ?? "Saved resource"}</p></div><button className="favorite-button" onClick={async () => { const updated = await api.resources.update(resource.id, { isFavorite: !resource.isFavorite }); setResource({ ...resource, ...updated }); }} aria-label="Toggle favorite">{resource.isFavorite ? "♥" : "♡"}</button></div><div className="detail-grid"><section className="detail-panel"><form className="detail-edit-form" onSubmit={saveDetails}><label><span className="eyebrow">Description</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={5} /></label><label><span className="eyebrow">Notes</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} placeholder="Keep a useful thought here." /></label><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save details"} <Icon name="check" size={14} /></button></form></section><aside className="detail-panel"><p className="eyebrow">Source</p>{resource.sourceUrl ? <a className="source-chip" href={resource.sourceUrl} target="_blank" rel="noreferrer">Open original <Icon name="external" size={12} /></a> : <p className="detail-copy">No source URL</p>}<p className="eyebrow detail-label-gap">Added</p><p className="detail-copy">{new Date(resource.createdAt).toLocaleString("en-IN")}</p><div className="detail-actions"><button className="danger-button" type="button" onClick={deleteResource} disabled={actionBusy}>Delete resource</button></div></aside></div></>}
  </div></NuseShell>;
}

function formatCategory(category: ResourceDetail["category"]): string {
  return category === "ai_tool" ? "AI tools" : category === "developer_resource" ? "Developer resources" : category.charAt(0).toUpperCase() + category.slice(1);
}
