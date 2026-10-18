from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import AdmissionAsk
from app.services.llm_parser import NaturalLanguageParser


def test_parser_only_endpoint_requires_service_token_and_never_calls_spring(monkeypatch):
    async def fake_extract(self, question, limit):
        return AdmissionAsk(grade="2.6", major="컴퓨터", region="서울", limit=limit)

    monkeypatch.setattr(NaturalLanguageParser, "extract", fake_extract)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, internal_service_token="secret-for-test")
    try:
        with TestClient(app) as client:
            body = {"question": "내신 2.6 서울 컴퓨터공학 어디 있지?", "limit": 4}
            assert client.post("/api/v1/ai/parse", json=body).status_code == 401
            result = client.post("/api/v1/ai/parse", json=body,
                headers={"X-Internal-Service-Token": "secret-for-test"})
            assert result.status_code == 200, result.text
            assert result.json()["grade"] == "2.6"
            assert result.json()["region"] == "서울"
            assert result.json()["limit"] == 4
            assert "answer" not in result.json()
    finally:
        app.dependency_overrides.clear()
