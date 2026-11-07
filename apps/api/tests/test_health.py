from fastapi.testclient import TestClient

from hub.main import app


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
