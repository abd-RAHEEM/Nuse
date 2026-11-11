import pytest
from fastapi import HTTPException

from hub.modules.capture.router import build_result, normalize_url, source_kind
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


def test_normalize_url_removes_tracking_and_default_port_but_keeps_job_identity() -> None:
    _, normalized = normalize_url(
        "HTTPS://boards.greenhouse.io:443/acme/jobs/42"
        "?utm_source=mail&gh_jid=42&ref=tracker&z=2&a=1#details"
    )

    assert normalized == "https://boards.greenhouse.io/acme/jobs/42?a=1&gh_jid=42&z=2"


def test_normalize_url_keeps_root_slash_and_brackets_ipv6_hosts() -> None:
    assert normalize_url("https://example.com/")[1] == "https://example.com/"
    assert normalize_url("https://[2606:4700:4700::1111]:443/")[1] == (
        "https://[2606:4700:4700::1111]/"
    )


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("lnkd.in", "linkedin"),
        ("www.linkedin.com", "linkedin"),
        ("m.linkedin.com", "linkedin"),
        ("www.instagram.com", "instagram"),
        ("linkedin.com.attacker.example", "other"),
        ("example.com", "other"),
    ],
)
def test_source_detection_blocks_social_sources_and_short_links(
    domain: str, expected: str
) -> None:
    assert source_kind(domain) == expected


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
