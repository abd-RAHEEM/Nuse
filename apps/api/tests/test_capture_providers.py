from hub.modules.capture.providers import parse_document
from hub.modules.capture.schemas import CreateExtractionRequest


def test_job_json_ld_maps_structured_fields() -> None:
    payload = CreateExtractionRequest(type="job", url="https://jobs.example/role")
    body = """
    <html><head>
      <script type="application/ld+json">
      {"@type":"JobPosting","title":"Platform Engineer",
       "hiringOrganization":{"name":"Northstar Labs"},
       "jobLocation":{"address":{"addressLocality":"Pune","addressCountry":"IN"}},
       "employmentType":"FULL_TIME","identifier":{"value":"N-42"},
       "description":"Build reliable services.","validThrough":"2026-12-01"}
      </script>
    </head><body>Platform Engineer</body></html>
    """
    result, trace = parse_document(payload, body, "text/html", payload.url)
    assert result["company"]["value"] == "Northstar Labs"
    assert result["location"]["value"] == "Pune, IN"
    assert result["externalJobId"]["value"] == "N-42"
    assert result["description"]["provenance"] == "extracted"
    assert trace["jsonld_jobposting"] == "done"


def test_resource_metadata_maps_title_description_and_category() -> None:
    payload = CreateExtractionRequest(type="resource", url="https://example.com/course")
    body = """
    <html><head>
      <title>Python course for data teams</title>
      <meta property="og:description" content="A practical course for Python teams">
    </head><body>Lesson material</body></html>
    """
    result, trace = parse_document(payload, body, "text/html", payload.url)
    assert result["title"]["value"] == "Python course for data teams"
    assert result["description"]["value"] == "A practical course for Python teams"
    assert result["category"]["value"] == "course"
    assert result["category"]["provenance"] == "suggested"
    assert trace["html_metadata"] == "done"


def test_plain_text_provider_keeps_missing_job_company_unset() -> None:
    payload = CreateExtractionRequest(type="job", text="Backend engineer\nBuild APIs.")
    result, trace = parse_document(payload, payload.text or "", "text/plain", None)
    assert result["title"]["value"] == "Backend engineer"
    assert result["company"]["value"] is None
    assert result["company"]["provenance"] == "not_found"
    assert trace == {"plain_text": "done"}
