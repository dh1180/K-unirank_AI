import asyncio
import json
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from app.config import Settings, get_settings
from app.main import app
from app.models import AdmissionAsk, SpringComparison
from app.services.harness import AdmissionHarness
from app.services.llm_parser import IntentExtractionError, MissingGrade, NaturalLanguageParser


def settings(api_key="fake-unit-test-key"):
    return Settings(_env_file=None, internal_service_token="test-private-key",
                    openai_api_key=api_key, llm_model="gpt-4.1-mini")


class FakeResponse:
    def __init__(self, message):
        self.message = message

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": json.dumps(self.message)}}]}


class FakeClient:
    def __init__(self, message):
        self.message = message
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, headers, json):
        self.request = (url, headers, json)
        return FakeResponse(self.message)


def test_llm_parser_uses_strict_schema_with_fixed_endpoint(monkeypatch):
    reply = {"grade": 2.8, "year": 2026, "track": "holistic",
             "special": "exclude", "scope": "near", "region": "서울", "major": "컴퓨터"}
    fake = FakeClient(reply)
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", lambda **kw: fake)
    filters = asyncio.run(NaturalLanguageParser(settings()).extract(
        "내신 2.8, 2026 서울 컴퓨터공학 학생부종합전형 알려줘", 4
    ))
    assert isinstance(filters, AdmissionAsk)
    assert filters.grade == Decimal("2.8")
    assert filters.track == "holistic"
    assert filters.limit == 4
    url, headers, body = fake.request
    assert url == NaturalLanguageParser.ENDPOINT
    assert headers["Authorization"] == "Bearer fake-unit-test-key"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_completion_tokens"] <= 220


def test_llm_missing_grade_requests_explicit_input(monkeypatch):
    reply = {"grade": None, "year": None, "track": "student",
             "special": "exclude", "scope": "near", "region": None, "major": None}
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", lambda **kw: FakeClient(reply))
    with pytest.raises(MissingGrade):
        asyncio.run(NaturalLanguageParser(settings()).extract("어느 대학 가면 좋을까?", 5))


def test_llm_rejects_invalid_or_invented_fields(monkeypatch):
    reply = {"grade": 2.8, "year": None, "track": "student",
             "special": "exclude", "scope": "near", "region": None,
             "major": None, "sql": "DROP TABLE admissions"}
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", lambda **kw: FakeClient(reply))
    with pytest.raises(IntentExtractionError):
        asyncio.run(NaturalLanguageParser(settings()).extract("내신 2.8 조건 검색해줘", 5))


def test_llm_fails_closed_when_api_key_missing():
    with pytest.raises(IntentExtractionError):
        asyncio.run(NaturalLanguageParser(settings(api_key="")).extract("내신 3.2 조건 검색해줘", 5))


def test_question_endpoint_returns_spring_grounded_evidence(monkeypatch):
    async def parse(self, question, limit):
        return AdmissionAsk(grade="2.5", year=2026, major="컴퓨터", limit=limit)
    async def comparison(self, request):
        return SpringComparison.model_validate({
            "selectedYear": 2026, "totalCount": 1,
            "items": [{
                "resultId": 19, "universityId": 2, "universityName": "가상대학교",
                "recruitmentUnitId": 31, "recruitmentUnitName": "컴퓨터학과",
                "selectionCategory": "학생부교과", "selectionName": "일반",
                "referenceCut": "2.75", "referenceBasis": "70% 컷",
                "sourceType": "ADIGA", "sourceName": "대입정보포털",
                "positionLabel": "앞섬", "positionTone": "ahead",
            }],
        })
    monkeypatch.setattr(NaturalLanguageParser, "extract", parse)
    monkeypatch.setattr("app.services.spring_client.SpringAdmissionTool.compare", comparison)
    app.dependency_overrides[get_settings] = settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/ai/questions", json={
                "question": "내신 2.5로 2026 컴퓨터학과를 찾아줘", "limit": 2,
            }, headers={"X-Internal-Service-Token": "test-private-key"})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["parsed_filters"]["major"] == "컴퓨터"
            assert data["result"]["evidence"][0]["reference_cut"] == "2.75"
            assert data["pipeline"] == [
                "llm.parse_intent", "spring.admissions.compare", "evidence.compose"
            ]
            assert "2.75등급" in data["result"]["answer"]
    finally:
        app.dependency_overrides.clear()
