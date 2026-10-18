from fastapi.testclient import TestClient
import pytest

from app.config import Settings, get_settings
from app.main import app
from app.rag import DocumentSearch, SearchQuery, chunks, validated_url


def test_page_and_year_filter_preserve_citations(tmp_path):
    index = DocumentSearch(str(tmp_path / "docs.sqlite3"))
    args = dict(university="예시대학교", year=2026, title="2026 모집요강",
                source_url="https://admissions.example.ac.kr/2026.pdf",
                fingerprint="verified-content")
    pages = [(1, "지원자격과 수능최저학력기준"), (2, "학생부종합 서류평가 면접")]
    assert index.ingest_pages(pages, **args) == 2
    assert index.ingest_pages(pages, **args) == 0
    result = index.search(SearchQuery(question="학생부종합", university="예시대학교", year=2026))
    assert result[0].page == 2
    assert result[0].source_url.endswith("#page=2")
    assert not index.search(SearchQuery(question="학생부종합", year=2025))
    assert not index.search(SearchQuery(question="학생부종합", university="다른대학교"))


def test_query_cannot_inject_sql_or_fts_commands(tmp_path):
    index = DocumentSearch(str(tmp_path / "docs.sqlite3"))
    index.ingest_pages([(1, "학생부교과 면접 일정")], university="예시대학교", year=2026,
        title="공식 안내", source_url="https://admissions.example.ac.kr/doc.pdf", fingerprint="sha")
    assert isinstance(index.search(SearchQuery(question='학생부교과" OR DROP TABLE passages')), list)
    assert len(index.search(SearchQuery(question="학생부교과"))) == 1


def test_rejects_unreviewed_url_schemes():
    for url in ("http://example.ac.kr/a.pdf", "file:///tmp/a.pdf", "https://localhost/test.pdf"):
        with pytest.raises(ValueError):
            validated_url(url)


def test_endpoint_requires_service_token(tmp_path):
    path = str(tmp_path / "docs.sqlite3")
    DocumentSearch(path).ingest_pages([(12, "서류평가 학생부종합")],
        university="예시대학", year=2026, title="전형 안내",
        source_url="https://example.ac.kr/guide.pdf", fingerprint="first")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, internal_service_token="test-token", rag_db_path=path)
    try:
        with TestClient(app) as client:
            params = {"question": "서류평가", "year": 2026}
            assert client.post("/api/v1/ai/docs/search", json=params).status_code == 401
            response = client.post("/api/v1/ai/docs/search", json=params,
                    headers={"X-Internal-Service-Token": "test-token"})
            assert response.status_code == 200, response.text
            assert response.json()["passages"][0]["page"] == 12
    finally:
        app.dependency_overrides.clear()
