import pytest
from fastapi import HTTPException

from hub.modules.capture.router import build_result, normalize_url
from hub.modules.capture.schemas import CreateExtractionRequest


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.8/metadata",
        "http://169.254.169.254/latest",
        "http://[::1]/",
        "http://localhost:8000/",
        "http://service.local/",
    ],
)
def test_normalize_url_rejects_local_and_private_targets(url: str) -> None:
    with pytest.raises(HTTPException) as error:
        normalize_url(url)
    assert error.value.status_code == 422
    assert "unsafe_url" in str(error.value.detail)


def test_normalize_url_keeps_public_url_and_removes_fragment() -> None:
    original, normalized = normalize_url("HTTPS://Example.com/jobs/#details")
    assert original == "HTTPS://Example.com/jobs/#details"
    assert normalized == "https://example.com/jobs"


def test_job_text_capture_does_not_invent_company() -> None:
    result = build_result(
        CreateExtractionRequest(
            type="job",
            text="Senior Python Engineer\nBuild reliable data systems.",
        ),
        None,
    )
    assert result["company"] == {"value": None, "provenance": "not_found"}
    assert result["title"]["value"] == "Senior Python Engineer"
