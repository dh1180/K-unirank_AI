from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import SpringComparison
from app.services.spring_client import SpringAdmissionTool, SpringToolFailure


def _settings(token="test-service-secret"):
    return Settings(
        _env_file=None,
        internal_service_token=token,
        spring_api_base_url="http://127.0.0.1:8080",
    )


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = _settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_does_not_require_service_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ai_endpoint_requires_token_even_if_not_configured(client):
    payload = {"grade": "2.5"}
    url = "/api/v1/ai/admissions/compare"
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, json=payload, headers={"X-Internal-Service-Token": "wrong"}).status_code == 401
    app.dependency_overrides[get_settings] = lambda: _settings("")
    response = client.post(url, json=payload, headers={"X-Internal-Service-Token": "anything"})
    assert response.status_code == 503


def test_harness_returns_only_verified_rows_and_links(client, monkeypatch):
    captured = []

    async def fake_compare(self, request):
        captured.append(request)
        return SpringComparison.model_validate({
            "selectedYear": 2026,
            "totalCount": 1,
            "items": [{
                "resultId": 123,
                "universityId": 1,
                "universityName": "예시대학교",
                "recruitmentUnitId": 71,
                "recruitmentUnitName": "컴퓨터공학과",
                "selectionCategory": "학생부교과",
                "selectionName": "일반전형",
                "referenceCut": "2.70",
                "referenceBasis": "70% 컷",
                "sourceType": "ADIGA",
                "sourceName": "대입정보포털",
                "positionLabel": "앞섬",
                "positionTone": "ahead",
            }],
        })

    monkeypatch.setattr(SpringAdmissionTool, "compare", fake_compare)
    response = client.post(
        "/api/v1/ai/admissions/compare",
        headers={"X-Internal-Service-Token": "test-service-secret"},
        json={"grade": "2.5", "year": 2026, "track": "student", "major": "컴퓨터"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["grounded"] is True
    assert data["tool_calls"] == ["spring.admissions.compare"]
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["url"] == "https://k-unirank.com/admissions/unit/71/"
    assert "2.70등급" in data["answer"]
    assert "확정적 예측이 아닙니다" in data["answer"]
    assert len(captured) == 1
    assert captured[0].major == "컴퓨터"
    assert captured[0].grade == Decimal("2.5")


def test_empty_result_never_invents_universities(client, monkeypatch):
    async def empty_result(self, request):
        return SpringComparison(selectedYear=None, totalCount=0, items=[])

    monkeypatch.setattr(SpringAdmissionTool, "compare", empty_result)
    response = client.post(
        "/api/v1/ai/admissions/compare",
        headers={"X-Internal-Service-Token": "test-service-secret"},
        json={"grade": "3.2"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["evidence"] == []
    assert "확인되지 않았습니다" in data["answer"]


def test_rejects_invalid_grade_and_unbounded_limits(client):
    url = "/api/v1/ai/admissions/compare"
    headers = {"X-Internal-Service-Token": "test-service-secret"}
    for payload in ({"grade": "0.5"}, {"grade": "10"}, {"grade": "2.5", "limit": 100}):
        response = client.post(url, headers=headers, json=payload)
        assert response.status_code == 422


def test_spring_failure_returns_safe_502(client, monkeypatch):
    async def fail(self, request):
        raise SpringToolFailure("Spring Boot 입결 API 연결 또는 응답 검증 실패")

    monkeypatch.setattr(SpringAdmissionTool, "compare", fail)
    response = client.post(
        "/api/v1/ai/admissions/compare",
        headers={"X-Internal-Service-Token": "test-service-secret"},
        json={"grade": "2.5"},
    )
    assert response.status_code == 502
    assert "Spring Boot" in response.json()["detail"]
