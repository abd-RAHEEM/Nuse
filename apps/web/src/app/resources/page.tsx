"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { NuseShell, Icon } from "@/components/nuse-shell";
import { api, apiMode } from "@/lib/api/client";
import type { ResourceSummary } from "@/types/api";

const resources = [
  ["AI tools", "PydanticAI", "Build agentic workflows with type-safe Python", "pydantic.dev", "Today"],
  ["Courses", "Practical Deep Learning for Coders", "A hands-on path from models to deployment", "fast.ai", "Yesterday"],
  ["Research", "Attention is all you need", "The paper that changed the shape of language models", "arxiv.org", "Oct 28"],
  ["Developer resources", "The ML engineer’s field guide", "A living collection of useful patterns and references", "github.com", "Oct 25"],
];

export default function ResourcesPage() {
  const [liveResources, setLiveResources] = useState<ResourceSummary[] | null>(null);
  const [liveError, setLiveError] = useState("");
  const [category, setCategory] = useState("All");
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState<ResourceSummary["category"]>("article");
  const [newUrl, setNewUrl] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [notionReady, setNotionReady] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState("");
  const categories = ["All", "AI tools", "Courses", "Research", "Developer resources"];
  useEffect(() => {
    if (apiMode !== "live") return;
    api.resources.list().then((result) => setLiveResources(result.items)).catch(() => {
      setLiveError("The live resource library could not be loaded. Check that the API is running.");
    });
    api.integrations.list().then(({ items }) => {
      const notion = items.find((item) => item.provider === "notion");
      setNotionReady(notion?.status === "connected" && Boolean(notion.config.databaseId));
    }).catch(() => {
      setLiveError("The Notion connection status could not be checked.");
    });
  }, []);
  const visibleLive = (liveResources ?? []).filter((item) => (category === "All" || formatCategory(item.category) === category) && `${item.title} ${item.description ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  const visibleMock = resources.filter(([itemCategory, title, description]) => (category === "All" || itemCategory === category) && `${title} ${description}`.toLowerCase().includes(query.toLowerCase()));
  const saveResource = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (apiMode !== "live" || !newTitle.trim()) return;
    setSaving(true);
    try {
      const created = await api.resources.create({
        title: newTitle.trim(),
        category: newCategory,
        sourceUrl: newUrl.trim() || undefined,
        description: newDescription.trim() || undefined,
      });
      setLiveResources((current) => [created, ...(current ?? [])]);
      setAddOpen(false);
      setNewTitle("");
      setNewUrl("");
      setNewDescription("");
    } catch {
      setLiveError("The resource could not be saved. Check the fields and try again.");
    } finally {
      setSaving(false);
    }
  };
  const toggleFavorite = async (item: ResourceSummary) => {
    if (apiMode !== "live") return;
    try {
      const updated = await api.resources.update(item.id, { isFavorite: !item.isFavorite });
      setLiveResources((current) => (current ?? []).map((resource) => resource.id === item.id ? updated : resource));
    } catch {
      setLiveError("The favorite state could not be updated.");
    }
  };
  const removeResource = async (item: ResourceSummary) => {
    if (apiMode !== "live") return;
    try {
      await api.resources.remove(item.id);
      setLiveResources((current) => (current ?? []).filter((resource) => resource.id !== item.id));
    } catch {
      setLiveError("The resource could not be deleted.");
    }
  };
  const exportResource = async (item: ResourceSummary) => {
    setExportingId(item.id);
    setExportMessage("");
    try {
      const { results } = await api.integrations.exportToNotion([item.id]);
      const result = results[0];
      if (!result || result.status === "failed") {
        setExportMessage(result?.error ?? "Notion did not return an export result.");
      } else {
        setExportMessage(`Exported “${item.title}” to Notion.`);
      }
    } catch {
      setExportMessage("The resource could not be exported. Check your Notion connection and database.");
    } finally {
      setExportingId(null);
    }
  };
  return <NuseShell title="Resources" eyebrow="A library for useful things">
    <div className="resources-stack">
      <div className="page-intro-row">
        <div>
          <p className="page-support">{liveError || (apiMode === "live" ? `${liveResources?.length ?? "—"} saved resources` : "42 saved resources · 8 waiting to be reviewed")}</p>
          {exportMessage && <p className="page-support" role="status">{exportMessage}</p>}
        </div>
        <div className="view-actions">
          <button className="quiet-button"><Icon name="sliders" size={15} /> More filters</button>
          <button className="primary-button" onClick={() => setAddOpen(true)}><Icon name="plus" size={15} /> Add resource</button>
        </div>
      </div>
      <div className="resource-filter-panel">
        <span className="eyebrow">Filter the library</span>
        <label className="search-field"><span>/</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search resources" /></label>
        <div className="resource-categories">{categories.map((item) => <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item} <span>{item === "All" ? (liveResources?.length ?? 42) : ""}</span></button>)}</div>
      </div>
      <div className="resource-ledger">
        {apiMode === "live" ? visibleLive.map((item) => <article className="resource-ledger-row" key={item.id}>
          <span className="resource-glyph">◫</span>
          <span className="row-main"><small className="category-label">{formatCategory(item.category)}</small><Link href={`/resources/${item.id}`}><strong>{item.title}</strong></Link><span>{item.description ?? "No description yet"}</span></span>
          <span className="resource-source">{item.sourcePlatform ?? "Saved resource"}</span>
          <span className="row-date">{new Date(item.createdAt).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
          <button className="favorite-button" onClick={() => toggleFavorite(item)} aria-label={`${item.isFavorite ? "Unfavorite" : "Favorite"} ${item.title}`}>{item.isFavorite ? "♥" : "♡"}</button>
          <button className="text-button" onClick={() => void exportResource(item)} disabled={!notionReady || exportingId === item.id} title={notionReady ? "Export this resource to Notion" : "Connect Notion and choose a database in Settings"}>{exportingId === item.id ? "Exporting…" : "Notion"}</button>
          <button className="text-button" onClick={() => void removeResource(item)}>Delete</button>
        </article>) : visibleMock.map(([itemCategory, title, description, source, date]) => <article className="resource-ledger-row" key={title}>
          <span className="resource-glyph">◫</span><span className="row-main"><small className="category-label">{itemCategory}</small><strong>{title}</strong><span>{description}</span></span>
          <span className="resource-source">{source}</span><span className="row-date">{date}</span><button className="favorite-button" aria-label={`Favorite ${title}`}>♡</button>
        </article>)}
      </div>
      {addOpen && <div className="sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddOpen(false); }}>
        <section className="capture-sheet" role="dialog" aria-modal="true" aria-labelledby="add-resource-title">
          <div className="sheet-grip" /><div className="sheet-header"><div><p className="eyebrow">Add to the library</p><h2 id="add-resource-title">Keep a useful thing close.</h2></div><button className="icon-button" onClick={() => setAddOpen(false)} aria-label="Close add resource">×</button></div>
          <form className="auth-form" onSubmit={saveResource}>
            <label>Title<input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} required /></label>
            <label>Category<select value={newCategory} onChange={(event) => setNewCategory(event.target.value as ResourceSummary["category"])}><option value="article">Article</option><option value="ai_tool">AI tool</option><option value="course">Course</option><option value="certification">Certification</option><option value="research">Research</option><option value="developer_resource">Developer resource</option><option value="other">Other</option></select></label>
            <label>Source URL<input type="url" value={newUrl} onChange={(event) => setNewUrl(event.target.value)} placeholder="https://..." /></label>
            <label>Description<textarea value={newDescription} onChange={(event) => setNewDescription(event.target.value)} rows={4} /></label>
            <button className="primary-button wide" type="submit" disabled={saving}>{saving ? "Saving resource…" : "Save resource"} <Icon name="arrow" size={15} /></button>
          </form>
        </section>
      </div>}
    </div>
  </NuseShell>;
}

function formatCategory(category: ResourceSummary["category"]): string {
  return category === "ai_tool" ? "AI tools" : category === "developer_resource" ? "Developer resources" : category.charAt(0).toUpperCase() + category.slice(1);
}
