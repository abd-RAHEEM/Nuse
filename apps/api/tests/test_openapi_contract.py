import json
from pathlib import Path

from hub.main import app


def test_generated_openapi_has_approved_paths_and_camel_case_projections() -> None:
    spec = app.openapi()
    paths = spec["paths"]
    expected = {
        "/api/v1/jobs",
        "/api/v1/jobs/check-duplicate",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/events",
        "/api/v1/jobs/{job_id}/events/{event_id}",
        "/api/v1/resources",
        "/api/v1/resources/{resource_id}",
        "/api/v1/tags",
        "/api/v1/tags/{tag_id}",
        "/api/v1/collections",
        "/api/v1/collections/{collection_id}",
        "/api/v1/collections/{collection_id}/resources/{resource_id}",
        "/api/v1/dashboard",
        "/api/v1/settings",
        "/api/v1/exports/jobs",
        "/api/v1/exports/resources",
        "/api/v1/integrations/gmail/oauth/start",
        "/api/v1/integrations/gmail/oauth/callback",
        "/api/v1/integrations/gmail",
        "/api/v1/integrations/gmail/sync",
        "/api/v1/integrations/gmail/sync/{run_id}/step",
        "/api/v1/integrations/gmail/review",
        "/api/v1/integrations/gmail/review/{message_id}",
    }
    assert expected <= paths.keys()
    assert paths["/api/v1/integrations/gmail"]["delete"]["operationId"].startswith(
        "disconnect_gmail"
    )

    schemas = spec["components"]["schemas"]
    assert {
        "JobSummaryResponse",
        "JobDetailResponse",
        "ResourceSummaryResponse",
        "ResourceDetailResponse",
        "CollectionResponse",
        "TagResponse",
        "GmailSyncRunResponse",
        "GmailReviewItem",
        "GmailReviewRequest",
    } <= schemas.keys()
    assert "nextCursor" in schemas["JobPageResponse"]["properties"]
    assert "sourceUrl" in schemas["ResourceSummaryResponse"]["properties"]
    assert "collectionIds" in schemas["ResourceSummaryResponse"]["properties"]
    assert "resourceCount" in schemas["CollectionResponse"]["properties"]
    assert "jobCount" in schemas["TagResponse"]["properties"]
    assert "resourceCount" in schemas["TagResponse"]["properties"]
    assert "tags" in schemas["JobSummaryResponse"]["properties"]
    assert "displayName" in schemas["UserResponse"]["properties"]
    assert "createdAt" in schemas["UserResponse"]["properties"]
    assert "recentActivity" in schemas["DashboardResponse"]["properties"]
    assert "applicationsTracked" in schemas["DashboardCounts"]["properties"]


def test_committed_openapi_matches_runtime_shape() -> None:
    committed = json.loads(
        (Path(__file__).parents[3] / "contracts" / "openapi.json").read_text()
    )
    assert set(committed["paths"]) == set(app.openapi()["paths"])
