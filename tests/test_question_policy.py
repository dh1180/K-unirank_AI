import asyncio
from decimal import Decimal

import httpx
import pytest

from app.services.question_policy import ExplicitQuestion, QuestionClarification
from app.services.llm_parser import NaturalLanguageParser
from app.config import Settings


@pytest.mark.parametrize("question,grade,region,major,track,university", [
    ("내신 3.2인데 수도권 컴공 교과로 찾아줘", "3.2", "서울,경기,인천", "컴퓨터,소프트웨어,컴퓨팅", "student", None),
    ("내신은 2점8인데 서울 경기 심리학과 학종 궁금해", "2.8", "서울,경기", "심리", "holistic", None),
    ("내신 3.0 서울대 심리학과 알려줘", "3.0", None, "심리", "student", "서울대학교"),
    ("내신 2.5 항공대 컴공 교과 찾아줘", "2.5", None, "컴퓨터,소프트웨어,컴퓨팅", "student", "한국항공대학교"),
    ("내신 4.1 서울 말고 부산 간호학과", "4.1", "부산", "간호", "student", None),
    ("내신 3.7 경상남도 기계학과", "3.7", "경남", "기계", "student", None),
    ("내신 2.6 유아교육학과 찾아줘", "2.6", None, "유아교육", "student", None),
    ("내신 2.6 국어국문학과 찾아줘", "2.6", None, "국어국문학", "student", None),
    ("내신 1.3 수의대 찾아줘", "1.3", None, "수의예,수의학", "student", None),
    ("내신 3.1 컴퓨터 말고 기계학과", "3.1", None, "기계", "student", None),
])
def test_grounded_constraints(question, grade, region, major, track, university):
    parsed = ExplicitQuestion.read(question)
    assert (parsed.grade, parsed.region, parsed.major, parsed.track, parsed.university) == (Decimal(grade), region, major, track, university)


@pytest.mark.parametrize("question,detail", [
    ("정시 평균 백분위 88로 컴공 찾아줘", "9등급제"),
    ("5등급제 내신 2.5 컴공 찾아줘", "5등급제"),
    ("내신 2등급 초반 컴공", "정확한"),
    ("내신 2~3등급 컴공", "정확한"),
    ("내신 2.8 또는 내신 3.5 컴공", "하나"),
    ("내신 3.0 교과와 학종 간호", "전형 하나"),
    ("내신 3.0 전문대 간호", "대학 유형"),
    ("내신 3.0 수능최저 없는 간호", "최저"),
    ("내신 3.0 기회균등만 간호", "특별전형만"),
    ("내신 3.0 컴퓨터 제외", "관심"),
    ("내신 3.0 서울대 제외 심리", "대학 제외"),
    ("내신 3.0 2025 2026 간호", "학년도"),
])
def test_unsupported_or_ambiguous_requests_need_clarification(question, detail):
    with pytest.raises(QuestionClarification, match=detail):
        ExplicitQuestion.read(question)


def test_model_cannot_replace_explicit_conditions():
    q = "내신 3.2 수도권 컴공 교과 찾아줘"
    parsed = ExplicitQuestion.read(q).resolve({"grade": 1, "year": 2025, "track": "holistic", "region": "부산", "major": "간호"}, q, 5)
    assert parsed["grade"] == Decimal("3.2")
    assert parsed["year"] is None and parsed["track"] == "student"
    assert parsed["region"] == "서울,경기,인천" and parsed["major"] == "컴퓨터,소프트웨어,컴퓨팅"
    assert parsed["notes"]


def test_defaults_and_explicit_special_and_scope():
    assert ExplicitQuestion.read("내신 3.0 간호 찾아줘").special == "exclude"
    parsed = ExplicitQuestion.read("내신 3.0 간호 특별전형 포함 전체 등급")
    assert parsed.special == "all" and parsed.scope == "all"


def test_provider_outage_uses_only_known_grounded_terms(monkeypatch):
    class Offline:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", lambda **kwargs: Offline())
    config = Settings(_env_file=None, openai_api_key="test")
    parsed = asyncio.run(NaturalLanguageParser(config).extract("내신 3.2 수도권 컴공 교과 찾아줘", 5))
    assert parsed.region == "서울,경기,인천" and parsed.major == "컴퓨터,소프트웨어,컴퓨팅"


def test_invalid_query_does_not_call_provider(monkeypatch):
    def unexpected(**kwargs): raise AssertionError("provider must not be called")
    monkeypatch.setattr("app.services.llm_parser.httpx.AsyncClient", unexpected)
    with pytest.raises(QuestionClarification, match="정시"):
        asyncio.run(NaturalLanguageParser(Settings(_env_file=None, openai_api_key="test")).extract("정시 백분위 88 컴공 찾아줘", 5))
