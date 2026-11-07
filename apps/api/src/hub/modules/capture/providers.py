import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from hub.modules.capture.schemas import CreateExtractionRequest


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[dict] = []
        self._in_title = False
        self._in_script = False
        self._script_type = ""
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()
        elif tag.lower() == "script":
            self._in_script = True
            self._script_type = values.get("type", "").lower()
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "script" and self._in_script:
            if self._script_type == "application/ld+json":
                try:
                    value = json.loads("".join(self._script_parts))
                except json.JSONDecodeError:
                    value = None
                if isinstance(value, dict):
                    self.json_ld.append(value)
                elif isinstance(value, list):
                    self.json_ld.extend(item for item in value if isinstance(item, dict))
            self._in_script = False
            self._script_type = ""
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_script:
            self._script_parts.append(data)
        elif data.strip():
            self.text_parts.append(data)


def _field(value: object, source: str, provenance: str = "extracted") -> dict:
    if value is None or value == "" or value == []:
        return {"value": None if value != [] else [], "provenance": "not_found"}
    return {"value": value, "provenance": provenance, "source": source}


def _first_json_ld(parser: _DocumentParser, type_name: str) -> dict:
    for item in parser.json_ld:
        types = item.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if type_name in types:
            return item
    return {}


def _plain_text(parser: _DocumentParser) -> str:
    return re.sub(r"\s+", " ", unescape(" ".join(parser.text_parts))).strip()


def _job_result(
    payload: CreateExtractionRequest,
    parser: _DocumentParser,
    url: str | None,
) -> dict:
    job = _first_json_ld(parser, "JobPosting")
    organization = job.get("hiringOrganization")
    company = organization.get("name") if isinstance(organization, dict) else None
    location = job.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    address = location.get("address") if isinstance(location, dict) else None
    if isinstance(address, dict):
        location = ", ".join(
            str(item)
            for item in (
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            )
            if item
        )
    else:
        location = None
    identifier = job.get("identifier")
    external_id = identifier.get("value") if isinstance(identifier, dict) else identifier
    text = _plain_text(parser)
    title = job.get("title") or parser.meta.get("og:title") or "".join(parser.title_parts).strip()
    description = job.get("description") or parser.meta.get("og:description") or text
    return {
        "type": "job",
        "company": _field(company, "json-ld"),
        "title": _field(title or None, "json-ld" if job.get("title") else "og:title"),
        "location": _field(location, "json-ld"),
        "employmentType": _field(job.get("employmentType"), "json-ld"),
        "workMode": _field(
            "remote" if job.get("jobLocationType") == "TELECOMMUTE" else None,
            "json-ld",
        ),
        "externalJobId": _field(external_id, "json-ld"),
        "description": _field(description, "json-ld" if job.get("description") else "html"),
        "requirements": _field(job.get("qualifications"), "json-ld"),
        "deadline": _field(job.get("validThrough"), "json-ld"),
        "sourceUrl": _field(url, "input"),
    }


def _resource_result(
    payload: CreateExtractionRequest,
    parser: _DocumentParser,
    url: str | None,
) -> dict:
    text = _plain_text(parser)
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title")
    title = title or "".join(parser.title_parts).strip() or (
        text.split(" ", 1)[0] if text else None
    )
    description = parser.meta.get("og:description") or parser.meta.get("description") or text
    domain = urlparse(url).hostname if url else None
    return {
        "type": "resource",
        "title": _field(title, "og:title" if parser.meta.get("og:title") else "html"),
        "category": _field(_suggest_category(title, description), "heuristic", "suggested"),
        "sourcePlatform": _field(domain, "url"),
        "description": _field(
            description,
            "og:description" if parser.meta.get("og:description") else "html",
        ),
        "summary": _field(None, "html"),
        "suggestedTags": _field([], "heuristic"),
        "details": _field(None, "html"),
        "sourceUrl": _field(url, "input"),
    }


def _suggest_category(title: str | None, description: str | None) -> str:
    text = f"{title or ''} {description or ''}".lower()
    if any(word in text for word in ("course", "tutorial", "learn")):
        return "course"
    if any(word in text for word in ("github", "repository", "developer", "api")):
        return "developer_resource"
    if any(word in text for word in ("research", "paper", "journal")):
        return "research"
    if any(word in text for word in ("article", "blog", "guide")):
        return "article"
    return "other"


def parse_document(
    payload: CreateExtractionRequest,
    body: str,
    content_type: str,
    url: str | None,
) -> tuple[dict, dict]:
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _DocumentParser()
        parser.feed(body)
        if payload.type == "job":
            return _job_result(payload, parser, url), {
                "jsonld_jobposting": "done" if _first_json_ld(parser, "JobPosting") else "skipped",
                "html_metadata": "done",
                "plain_text": "done",
            }
        return _resource_result(payload, parser, url), {
            "html_metadata": "done",
            "plain_text": "done",
        }
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    result = {
        "type": payload.type,
        "title": _field(first_line or None, "plain_text"),
        "description": _field(body.strip() or None, "plain_text"),
        "sourceUrl": _field(url, "input"),
    }
    if payload.type == "job":
        result.update(
            {
                "company": _field(None, "plain_text"),
                "location": _field(None, "plain_text"),
                "employmentType": _field(None, "plain_text"),
                "workMode": _field(None, "plain_text"),
                "externalJobId": _field(None, "plain_text"),
                "requirements": _field(None, "plain_text"),
                "deadline": _field(None, "plain_text"),
            }
        )
    else:
        result.update(
            {
                "category": _field("other", "heuristic", "suggested"),
                "sourcePlatform": _field(urlparse(url).hostname if url else None, "url"),
                "summary": _field(None, "plain_text"),
                "suggestedTags": _field([], "plain_text"),
                "details": _field(None, "plain_text"),
            }
        )
    return result, {"plain_text": "done"}
