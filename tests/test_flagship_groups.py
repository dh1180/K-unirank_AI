import asyncio
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.services.llm_parser import NaturalLanguageParser
from app.services.question_policy import REGIONAL_FLAGSHIPS, ExplicitQuestion, QuestionClarification


@pytest.mark.parametrize("alias", [
    "지거국", "지거국만", "지거국에서", "지 거 국", "지방거점국립대", "지방 거점 국립대만",
    "지방거점국립대학", "지방 거점 국립대학교", "지역거점국립대학교",
])
def test_regional_flagships_are_explicit_nine_universities(alias):
    parsed = ExplicitQuestion.read(f"내신 3.0 {alias} 컴공 교과 찾아줘")
    assert tuple(parsed.university.split(",")) == REGIONAL_FLAGSHIPS
    assert "서울대학교" not in parsed.university
    assert parsed.region is None
    assert parsed.grade == Decimal("3.0") and parsed.track == "student"
    assert parsed.major == "컴퓨터,소프트웨어,컴퓨팅"
    # A nested 거점국립대 substring must not claim a conflicting ten-member group.
    group_notes = [note for note in parsed.notes if "조건으로 검색" in note]
    assert len(group_notes) == 1 and "서울대학교" not in group_notes[0]


@pytest.mark.parametrize("alias", ["거점국립대", "거점국립대만", "국가 거점 국립대학교", "거점 국립대학", "KNU10"])
def test_explicit_national_group_includes_seoul_without_overrunning_limit(alias):
    parsed = ExplicitQuestion.read(f"{alias} 내신 2.8 심리 학종 찾아줘")
    assert tuple(parsed.university.split(",")) == ("서울대학교", *REGIONAL_FLAGSHIPS)
    assert parsed.track == "holistic" and parsed.region is None


def test_explicit_region_named_university_and_model_conflict_do_not_expand_scope():
    q = "내신 3.2 부산 지거국 컴공 교과 찾아줘"
    result = ExplicitQuestion.read(q).resolve({"university": "가천대학교", "region": "서울", "grade": 1}, q, 5)
    assert tuple(result["university"].split(",")) == REGIONAL_FLAGSHIPS
    assert result["region"] == "부산" and result["grade"] == Decimal("3.2")
    assert len(ExplicitQuestion.read("내신 3.0 지거국 서울대 찾아줘").university.split(",")) == 10
    assert ExplicitQuestion.read("내신 3.0 경상대 간호 교과").university == "경상국립대학교"
    assert ExplicitQuestion.read("내신 3.0 부경대 간호 교과").university == "국립부경대학교"


@pytest.mark.parametrize("question", [
    "내신 3.0 지거국 제외 컴공", "내신 3.0 지거국 이상 컴공",
    "내신 3.0 지거군 컴공", "내신 3.0 국립대만 컴공",
])
def test_ambiguous_unsupported_constraints_do_not_silently_become_national(question):
    with pytest.raises(QuestionClarification):
        ExplicitQuestion.read(question)


def test_provider_outage_still_preserves_regional_group(monkeypatch):
    class Offline:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", lambda **kwargs: Offline())
    result = asyncio.run(NaturalLanguageParser(Settings(_env_file=None, openai_api_key="test")).extract(
        "지거국 3.0등급으로 갈만한 학과 찾아줘", 5))
    assert tuple(result.university.split(",")) == REGIONAL_FLAGSHIPS
    assert result.major is None and result.region is None
