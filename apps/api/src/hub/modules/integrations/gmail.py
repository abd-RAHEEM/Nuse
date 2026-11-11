import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header
from email.utils import parseaddr

from hub.models import Job

MAX_BODY_CHARACTERS = 20_000
JOB_SEARCH_TERMS = (
    "application",
    "applied",
    "assessment",
    "interview",
    "offer",
    "recruitment",
    "hiring",
    "candidate",
    "position",
    "job",
)

_STAGE_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "rejected",
        (
            re.compile(r"\bregret to inform\b"),
            re.compile(r"\bnot moving forward\b"),
            re.compile(r"\bdecided not to proceed\b"),
            re.compile(r"\bunsuccessful\b"),
        ),
    ),
    (
        "offer",
        (
            re.compile(r"\boffer of employment\b"),
            re.compile(r"\bpleased to offer\b"),
            re.compile(r"\boffer letter\b"),
            re.compile(r"\bjob offer\b"),
            re.compile(r"\bemployment offer\b"),
        ),
    ),
    (
        "interview",
        (
            re.compile(r"\binterview\b"),
            re.compile(r"\bphone screen\b"),
        ),
    ),
    (
        "assessment",
        (
            re.compile(r"\bassessment\b"),
            re.compile(r"\bcoding challenge\b"),
            re.compile(r"\btechnical test\b"),
            re.compile(r"\bonline test\b"),
        ),
    ),
    (
        "applied",
        (
            re.compile(r"\bthank you for applying\b"),
            re.compile(r"\bapplication received\b"),
            re.compile(r"\bapplication submitted\b"),
            re.compile(r"\bwe received your application\b"),
            re.compile(r"\bsuccessfully applied\b"),
        ),
    ),
)


@dataclass(frozen=True)
class ParsedGmailMessage:
    message_id: str
    thread_id: str | None
    sender: str | None
    subject: str
    received_at: datetime
    body_text: str


def _decode_header(value: str) -> str:
    decoded: list[str] = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded).strip()


def _decode_body_part(data: object) -> str:
    if not isinstance(data, str):
        return ""
    encoded = data[:35_000]
    encoded += "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return ""


def _plain_text_parts(payload: dict) -> str:
    fragments: list[str] = []
    remaining = MAX_BODY_CHARACTERS

    def visit(part: dict) -> None:
        nonlocal remaining
        if remaining <= 0 or part.get("filename"):
            return
        if part.get("mimeType") == "text/plain":
            body = part.get("body")
            text = _decode_body_part(body.get("data") if isinstance(body, dict) else None)
            text = text[:remaining]
            if text:
                fragments.append(text)
                remaining -= len(text)
        children = part.get("parts")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    visit(child)

    visit(payload)
    return "\n".join(fragments)


def parse_gmail_message(message: dict) -> ParsedGmailMessage | None:
    message_id = message.get("id")
    internal_date = message.get("internalDate")
    try:
        if not isinstance(message_id, str) or not isinstance(internal_date, str):
            return None
        received_at = datetime.fromtimestamp(int(internal_date) / 1000, UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None

    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    raw_headers = payload.get("headers")
    headers: dict[str, str] = {}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if (
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("value"), str)
            ):
                headers[item["name"].casefold()] = _decode_header(item["value"])

    sender_header = headers.get("from", "")
    sender = parseaddr(sender_header)[1] or None
    return ParsedGmailMessage(
        message_id=message_id,
        thread_id=message.get("threadId")
        if isinstance(message.get("threadId"), str)
        else None,
        sender=sender[:500] if sender else None,
        subject=headers.get("subject", "")[:1000],
        received_at=received_at,
        body_text=_plain_text_parts(payload),
    )


def normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def match_job(text: str, jobs: list[Job]) -> Job | None:
    normalized_text = normalize_match_text(text)
    matches = [
        job
        for job in jobs
        if job.company
        and job.title
        and _contains_phrase(normalized_text, normalize_match_text(job.company))
        and _contains_phrase(normalized_text, normalize_match_text(job.title))
    ]
    return matches[0] if len(matches) == 1 else None


def classify_job_stage(text: str) -> str | None:
    normalized = normalize_match_text(text)
    for stage, patterns in _STAGE_PATTERNS:
        if any(pattern.search(normalized) for pattern in patterns):
            return stage
    return None
