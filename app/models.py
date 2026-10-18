"""Explicit typed inputs; LLMs never construct raw SQL or arbitrary URLs."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class AdmissionAsk(BaseModel):
    grade: Decimal = Field(ge=Decimal("1.0"), le=Decimal("9.0"), decimal_places=2)
    year: int | None = Field(default=None, ge=2000, le=2100)
    track: Literal["student", "holistic"] = "student"
    special: Literal["exclude", "all"] = "exclude"
    scope: Literal["near", "all"] = "near"
    region: str | None = Field(default=None, max_length=60)
    major: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=5, ge=1, le=10)


class NaturalLanguageQuestion(BaseModel):
    question: str = Field(min_length=8, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class NaturalLanguageAnswer(BaseModel):
    parsed_filters: AdmissionAsk
    result: "AdmissionAnswer"
    pipeline: list[str]


class SpringAdmissionRow(BaseModel):
    resultId: int
    universityId: int
    universityName: str
    recruitmentUnitId: int
    recruitmentUnitName: str
    selectionCategory: str
    selectionName: str
    referenceCut: Decimal
    referenceBasis: str
    sourceType: str
    sourceName: str
    cut50: Decimal | None = None
    cut70: Decimal | None = None
    positionLabel: str
    positionTone: str


class SpringComparison(BaseModel):
    selectedYear: int | None = None
    totalCount: int = Field(ge=0)
    items: list[SpringAdmissionRow]


class AdmissionEvidence(BaseModel):
    result_id: int
    university: str
    recruitment_unit: str
    selection: str
    source: str
    reference_basis: str
    reference_cut: Decimal
    url: str


class AdmissionAnswer(BaseModel):
    answer: str
    evidence: list[AdmissionEvidence]
    total_count: int
    selected_year: int | None
    tool_calls: list[str]
    grounded: Literal[True] = True
    disclaimer: str = "공개 입결 컷은 합격 확률이나 지원 자격을 보장하지 않습니다."
