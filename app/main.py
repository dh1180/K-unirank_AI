"""K-unirank's private AI gateway for Raspberry Pi 5 (ARM64)."""
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.config import Settings, get_settings
from app.models import AdmissionAnswer, AdmissionAsk
from app.services.harness import AdmissionHarness
from app.services.spring_client import SpringAdmissionTool, SpringToolFailure

app = FastAPI(
    title="K-unirank AI",
    version="0.1.0",
    description="Private evidence-grounded AI retrieval gateway; no open SQL execution",
    docs_url=None,
    redoc_url=None,
)


def require_internal_token(
    token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.internal_service_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서비스 인증 설정이 완료되지 않았습니다.",
        )
    if not token or not secrets.compare_digest(token, settings.internal_service_token):
        raise HTTPException(status_code=401, detail="인증되지 않은 서비스입니다.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ai/admissions/compare", response_model=AdmissionAnswer, dependencies=[
    Depends(require_internal_token)
])
async def compare_admissions(
    request: AdmissionAsk,
    settings: Settings = Depends(get_settings),
) -> AdmissionAnswer:
    try:
        harness = AdmissionHarness(SpringAdmissionTool(settings))
        return await harness.run(request)
    except SpringToolFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
