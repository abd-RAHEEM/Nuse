from fastapi.testclient import TestClient

from hub.main import app
from hub.modules.auth.schemas import AuthRequest


def test_health_is_public() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_explains_missing_database_configuration() -> None:
    response = TestClient(app).get("/health/ready")
    assert response.status_code in {200, 503}
    if response.status_code == 503:
        assert response.json()["reason"] in {
            "database_not_configured",
            "database_unavailable",
        }


def test_mutating_api_requests_require_csrf_header() -> None:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"username": "demo", "pin": "135790"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["requestId"]


def test_validation_errors_use_problem_details_without_echoing_input() -> None:
    response = TestClient(app).post(
        "/api/v1/auth/login",
        headers={"X-Requested-With": "hub"},
        json={"username": "private-user", "pin": "not-a-pin"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "validation_error"
    assert response.json()["requestId"]
    assert "private-user" not in response.text


def test_signup_accepts_camel_case_display_name() -> None:
    payload = AuthRequest.model_validate(
        {"username": "local.user", "pin": "748291", "displayName": "Local QA"}
    )
    assert payload.display_name == "Local QA"
