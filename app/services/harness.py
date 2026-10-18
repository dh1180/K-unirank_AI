"""Fixed-budget evidence harness: exactly one approved read-only data tool."""
from app.models import AdmissionAnswer, AdmissionAsk, AdmissionEvidence
from app.services.spring_client import SpringAdmissionTool


class AdmissionHarness:
    """Never invent a grade or determine admission probability."""

    def __init__(self, spring_tool: SpringAdmissionTool):
        self.spring_tool = spring_tool

    async def run(self, req: AdmissionAsk) -> AdmissionAnswer:
        # Hard tool budget = 1. No arbitrary tool calls or model-generated SQL.
        result = await self.spring_tool.compare(req)
        evidence = [
            AdmissionEvidence(
                result_id=row.resultId,
                university=row.universityName,
                recruitment_unit=row.recruitmentUnitName,
                selection=row.selectionName,
                source=f"{row.sourceType} · {row.sourceName}",
                reference_basis=row.referenceBasis,
                reference_cut=row.referenceCut,
                url=f"https://k-unirank.com/admissions/unit/{row.recruitmentUnitId}/",
            )
            for row in result.items[: req.limit]
        ]
        if not evidence:
            answer = "해당 검색 조건에서 비교 가능한 공개 입결이 확인되지 않았습니다."
        else:
            lines = [
                f"입력한 내신 {req.grade}등급을 공개된 입결 기준과 비교했습니다.",
                f"검색 조건과 일치하는 입결 {result.totalCount}건 중 {len(evidence)}건입니다.",
            ]
            for item in evidence:
                lines.append(
                    f"- {item.university} {item.recruitment_unit} "
                    f"({item.selection}): {item.reference_basis} {item.reference_cut}등급 "
                    f"[입결 확인]({item.url})"
                )
            lines.append("위 값은 과거 공개 입결이며 합격 가능성의 확정적 예측이 아닙니다.")
            answer = "\n".join(lines)
        return AdmissionAnswer(
            answer=answer,
            evidence=evidence,
            total_count=result.totalCount,
            selected_year=result.selectedYear,
            tool_calls=["spring.admissions.compare"],
        )
