import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from hub.modules.integrations import gmail_router
from hub.modules.integrations.gmail import (
    classify_job_stage,
    match_job,
    normalize_match_text,
    parse_gmail_message,
)
from hub.modules.integrations.gmail_router import (
    _can_auto_advance,
    _can_transition,
    disconnect_gmail,
    gmail_oauth_start,
)


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_gmail_message_parser_reads_plain_text_and_skips_attachments() -> None:
    message = parse_gmail_message(
        {
            "id": "message-1",
            "threadId": "thread-1",
            "internalDate": "1790000000000",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Hiring <team@example.com>"},
                    {"name": "Subject", "value": "Application received"},
                ],
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _encoded("We received your application.")},
                    },
                    {
                        "mimeType": "text/plain",
                        "filename": "resume.txt",
                        "body": {"data": _encoded("private attachment content")},
                    },
                ],
            },
        }
    )

    assert message is not None
    assert message.sender == "team@example.com"
    assert message.subject == "Application received"
    assert message.body_text == "We received your application."
    assert "private attachment" not in message.body_text


def test_gmail_parser_rejects_messages_without_a_valid_timestamp() -> None:
    assert parse_gmail_message(
        {"id": "message-1", "internalDate": "not-a-date", "payload": {}}
    ) is None


def test_job_match_requires_a_unique_company_and_role_match() -> None:
    jobs = [
        SimpleNamespace(company="Kite Systems", title="ML Platform Engineer"),
        SimpleNamespace(company="Kite Systems", title="ML Platform Engineer"),
    ]

    assert match_job(
        "Application received for ML Platform Engineer at Kite Systems", jobs
    ) is None
    assert match_job(
        "Application received for ML Platform Engineer at Kite Systems", jobs[:1]
    ) is jobs[0]
    assert match_job("Kite Systems role update", jobs[:1]) is None


def test_stage_classifier_prefers_terminal_outcome_and_skips_generic_updates() -> None:
    assert classify_job_stage(
        "We are pleased to offer you the role after your interview."
    ) == "offer"
    assert classify_job_stage("We are not moving forward after the interview.") == "rejected"
    assert classify_job_stage("Your application status has changed.") is None


def test_match_normalization_preserves_unicode_words() -> None:
    assert normalize_match_text("München—AI / Engineer") == "münchen ai engineer"


def test_email_updates_never_move_an_application_backward_automatically() -> None:
    assert _can_auto_advance("applied", "interview")
    assert not _can_auto_advance("interview", "assessment")
    assert _can_auto_advance("interview", "rejected")


def test_reviewed_stage_changes_follow_the_application_transition_rules() -> None:
    assert _can_transition("interview", "assessment")
    assert not _can_transition("assessment", "saved")
    assert _can_transition("rejected", "interview")


@pytest.mark.asyncio
async def test_disconnect_removes_matched_message_metadata() -> None:
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )

    response = await disconnect_gmail(
        SimpleNamespace(id=uuid4()),
        db,
    )

    assert response.status_code == 204
    assert db.execute.await_args.args[0].table.name == "gmail_processed_messages"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_gmail_oauth_start_initializes_new_connection_config(monkeypatch) -> None:
    user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    added_connections = []
    monkeypatch.setattr(
        gmail_router,
        "_gmail_connection",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        gmail_router,
        "get_settings",
        lambda: SimpleNamespace(
            google_client_id="client-id",
            google_client_secret="client-secret",
            google_gmail_redirect_uri=(
                "http://127.0.0.1:8000/api/v1/integrations/gmail/oauth/callback"
            ),
        ),
    )
    db.add.side_effect = added_connections.append

    response = await gmail_oauth_start(user, db)

    assert "accounts.google.com" in response.auth_url
    assert added_connections[0].config["oauthState"]
    db.commit.assert_awaited_once()
