"""K-unirank's private Railway AI intent gateway."""
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.config import Settings, get_settings
from app.models import AdmissionAnswer, AdmissionAsk, NaturalLanguageAnswer, NaturalLanguageQuestion
from app.rag import DocumentSearch, SearchQuery, SearchResult
from app.services.llm_parser import IntentExtractionError, MissingGrade, NaturalLanguageParser
from app.services.harness import AdmissionHarness
from app.services.spring_client import SpringAdmissionTool, SpringToolFailure
from app.services.request_budget import RequestBudget

budget = RequestBudget()


async def provider_budget(settings: Settings = Depends(get_settings)):
    await budget.enter(settings.daily_request_limit, settings.max_ai_concurrency)
    try:
        yield
    finally:
        await budget.leave()

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


@app.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    key = (settings.openrouter_api_key if settings.llm_provider == "openrouter"
           else settings.openai_api_key)
    if not key or len(settings.internal_service_token) < 32:
        raise HTTPException(503, "AI 연결 설정이 완료되지 않았습니다.")
    if settings.llm_provider == "openrouter" and not (
        settings.llm_model == "openrouter/free" or settings.llm_model.endswith(":free")
    ):
        raise HTTPException(503, "무료 모델 설정을 확인해 주세요.")
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


@app.post("/api/v1/ai/questions", response_model=NaturalLanguageAnswer, dependencies=[
    Depends(require_internal_token), Depends(provider_budget)
])
async def answer_natural_language(
    request: NaturalLanguageQuestion,
    settings: Settings = Depends(get_settings),
) -> NaturalLanguageAnswer:
    # LLM's only authority is parsing typed search filters; no SQL/URL or rating
    # figures from the model are trusted. The answer is composed from Spring evidence.
    try:
        parsed = await NaturalLanguageParser(settings).extract(request.question, request.limit)
        grounded = await AdmissionHarness(SpringAdmissionTool(settings)).run(parsed)
        return NaturalLanguageAnswer(
            parsed_filters=parsed,
            result=grounded,
            pipeline=["llm.parse_intent", "spring.admissions.compare", "evidence.compose"],
        )
    except MissingGrade as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntentExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpringToolFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/ai/docs/search", response_model=SearchResult,
          dependencies=[Depends(require_internal_token)])
async def search_documents(request: SearchQuery,
                           settings: Settings = Depends(get_settings)) -> SearchResult:
    passages = DocumentSearch(settings.rag_db_path).search(request)
    return SearchResult(passages=passages)


@app.post("/api/v1/ai/parse", response_model=AdmissionAsk,
          dependencies=[Depends(require_internal_token), Depends(provider_budget)])
async def parse_admission_question(
    request: NaturalLanguageQuestion,
    settings: Settings = Depends(get_settings),
) -> AdmissionAsk:
    """Spring asks for typed filters; this service has no database credentials."""
    try:
        return await NaturalLanguageParser(settings).extract(request.question, request.limit)
    except MissingGrade as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntentExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
